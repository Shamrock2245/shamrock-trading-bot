// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FlashArbReceiver
 * @notice Atomic flash loan arbitrage via Balancer V2 (0% fee, preferred) or Aave V3 (0.05% fee).
 *
 * Security guarantees:
 *   ✅ Atomic revert — entire tx reverts if profit < minExpectedProfit
 *   ✅ Zero capital at risk — borrowed funds returned in same tx
 *   ✅ Reentrancy guard — prevents recursive callback attacks
 *   ✅ Caller authentication — only owner can initiate; only Balancer/Aave can callback
 *   ✅ Initiator check on Aave callback — rejects spoofed callbacks
 *
 * Constructor args:
 *   _balancerVault  — Balancer V2 Vault (0xBA12...2C8, same on all chains)
 *   _aavePool       — Aave V3 Pool (chain-specific)
 *   _oneInchRouter  — 1inch V6 Aggregation Router (chain-specific)
 */

// ─────────────────────────────────────────────────────────────────────────────
// Interfaces
// ─────────────────────────────────────────────────────────────────────────────

interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address recipient, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IBalancerVault {
    function flashLoan(
        address recipient,
        address[] memory tokens,
        uint256[] memory amounts,
        bytes memory userData
    ) external;
}

interface IAavePool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

// ─────────────────────────────────────────────────────────────────────────────
// Contract
// ─────────────────────────────────────────────────────────────────────────────

contract FlashArbReceiver {

    // ── State ─────────────────────────────────────────────────────────────────
    address public immutable owner;
    address public immutable balancerVault;
    address public immutable aavePool;
    address public immutable oneInchRouter;

    // Reentrancy guard
    bool private _entered;

    // ── Structs ───────────────────────────────────────────────────────────────
    struct ArbParams {
        address flashToken;
        uint256 flashAmount;
        uint256 minExpectedProfit;  // Profit floor — tx reverts if not met
        bytes[] swapPayloads;       // Encoded calldata for each swap leg
        address[] swapRouters;      // Router address for each swap leg
    }

    // ── Events ────────────────────────────────────────────────────────────────
    event ArbExecuted(
        address indexed token,
        uint256 flashAmount,
        uint256 netProfit,
        address indexed flashProvider
    );

    // ── Modifiers ─────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier nonReentrant() {
        require(!_entered, "Reentrant call");
        _entered = true;
        _;
        _entered = false;
    }

    // ── Constructor ───────────────────────────────────────────────────────────
    constructor(
        address _balancerVault,
        address _aavePool,
        address _oneInchRouter
    ) {
        require(_balancerVault != address(0), "Zero balancer vault");
        require(_aavePool != address(0), "Zero aave pool");
        require(_oneInchRouter != address(0), "Zero 1inch router");
        owner = msg.sender;
        balancerVault = _balancerVault;
        aavePool = _aavePool;
        oneInchRouter = _oneInchRouter;
    }

    // ── Admin ─────────────────────────────────────────────────────────────────

    /// @notice Rescue any ERC-20 tokens accidentally sent to this contract.
    function withdrawToken(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        require(balance > 0, "Zero balance");
        IERC20(token).transfer(owner, balance);
    }

    /// @notice Rescue any ETH accidentally sent to this contract.
    function withdrawETH() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "Zero ETH balance");
        payable(owner).transfer(balance);
    }

    receive() external payable {}

    // ─────────────────────────────────────────────────────────────────────────
    // Balancer V2 Flash Loan (0% fee — preferred)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Initiate a Balancer V2 flash loan arb.
     * @param token            Token to borrow (e.g. USDC)
     * @param amount           Amount to borrow (in token decimals)
     * @param minExpectedProfit Minimum net profit required — reverts if not met
     * @param swapPayloads     Encoded swap calldata for each leg
     * @param swapRouters      Router address for each leg
     */
    function executeBalancerFlashArb(
        address token,
        uint256 amount,
        uint256 minExpectedProfit,
        bytes[] calldata swapPayloads,
        address[] calldata swapRouters
    ) external onlyOwner nonReentrant {
        require(swapPayloads.length > 0, "No swap payloads");
        require(swapPayloads.length == swapRouters.length, "Payload/router length mismatch");

        address[] memory tokens = new address[](1);
        tokens[0] = token;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;

        bytes memory userData = abi.encode(
            ArbParams({
                flashToken: token,
                flashAmount: amount,
                minExpectedProfit: minExpectedProfit,
                swapPayloads: swapPayloads,
                swapRouters: swapRouters
            })
        );

        IBalancerVault(balancerVault).flashLoan(address(this), tokens, amounts, userData);
    }

    /**
     * @notice Balancer V2 flash loan callback.
     *         Called by the Balancer Vault after transferring borrowed tokens.
     */
    function receiveFlashLoan(
        address[] memory, /* tokens — not used directly, read from ArbParams */
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external nonReentrant {
        require(msg.sender == balancerVault, "Caller is not Balancer Vault");

        ArbParams memory params = abi.decode(userData, (ArbParams));

        // Execute all swap legs with the borrowed capital
        _executeSwaps(params);

        uint256 endBalance = IERC20(params.flashToken).balanceOf(address(this));
        uint256 repaymentAmount = amounts[0] + feeAmounts[0];

        require(endBalance >= repaymentAmount, "Insufficient balance to repay Balancer");
        uint256 netProfit = endBalance - repaymentAmount;
        require(netProfit >= params.minExpectedProfit, "Arb unprofitable: below min profit floor");

        // Repay Balancer Vault (Balancer pulls via transfer in receiveFlashLoan)
        IERC20(params.flashToken).transfer(balancerVault, repaymentAmount);

        // Transfer net profit to owner
        if (netProfit > 0) {
            IERC20(params.flashToken).transfer(owner, netProfit);
            emit ArbExecuted(params.flashToken, params.flashAmount, netProfit, balancerVault);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Aave V3 Flash Loan (0.05% fee — fallback)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Initiate an Aave V3 flash loan arb.
     */
    function executeAaveFlashArb(
        address token,
        uint256 amount,
        uint256 minExpectedProfit,
        bytes[] calldata swapPayloads,
        address[] calldata swapRouters
    ) external onlyOwner nonReentrant {
        require(swapPayloads.length > 0, "No swap payloads");
        require(swapPayloads.length == swapRouters.length, "Payload/router length mismatch");

        bytes memory params = abi.encode(
            ArbParams({
                flashToken: token,
                flashAmount: amount,
                minExpectedProfit: minExpectedProfit,
                swapPayloads: swapPayloads,
                swapRouters: swapRouters
            })
        );

        IAavePool(aavePool).flashLoanSimple(address(this), token, amount, params, 0);
    }

    /**
     * @notice Aave V3 flash loan callback.
     *         Called by the Aave Pool after transferring borrowed tokens.
     */
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external nonReentrant returns (bool) {
        require(msg.sender == aavePool, "Caller is not Aave Pool");
        require(initiator == address(this), "Initiator is not this contract");

        ArbParams memory arbParams = abi.decode(params, (ArbParams));

        // Execute all swap legs with the borrowed capital
        _executeSwaps(arbParams);

        uint256 endBalance = IERC20(asset).balanceOf(address(this));
        uint256 repaymentAmount = amount + premium;

        require(endBalance >= repaymentAmount, "Insufficient balance to repay Aave");
        uint256 netProfit = endBalance - repaymentAmount;
        require(netProfit >= arbParams.minExpectedProfit, "Arb unprofitable: below min profit floor");

        // Approve Aave Pool to pull repayment (Aave uses transferFrom)
        IERC20(asset).approve(aavePool, repaymentAmount);

        // Transfer net profit to owner
        if (netProfit > 0) {
            IERC20(asset).transfer(owner, netProfit);
            emit ArbExecuted(asset, amount, netProfit, aavePool);
        }

        return true;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Internal: Swap Executor
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @dev Execute all swap legs. Each payload is pre-encoded calldata for the
     *      respective router (1inch, Uniswap V3, etc.). The Python arb_executor
     *      is responsible for encoding correct approvals into the payload or
     *      pre-approving routers. For safety, we approve max to the router before
     *      each call and reset to 0 after.
     */
    function _executeSwaps(ArbParams memory params) internal {
        for (uint256 i = 0; i < params.swapPayloads.length; i++) {
            address router = params.swapRouters[i];
            bytes memory payload = params.swapPayloads[i];

            require(router != address(0), "Zero router address");

            // Approve router to spend the flash token (covers first leg)
            // For multi-hop arbs, intermediate tokens are approved via the payload
            IERC20(params.flashToken).approve(router, type(uint256).max);

            (bool success, bytes memory returnData) = router.call(payload);
            if (!success) {
                // Bubble up revert reason if available
                if (returnData.length > 0) {
                    assembly {
                        revert(add(32, returnData), mload(returnData))
                    }
                }
                revert("Swap leg failed");
            }

            // Reset approval to 0 after each leg (security best practice)
            IERC20(params.flashToken).approve(router, 0);
        }
    }
}
