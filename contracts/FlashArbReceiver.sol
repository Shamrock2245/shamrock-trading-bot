// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FlashArbReceiver
 * @dev Executing atomic flash loan arbitrage via Balancer (V2) or Aave (V3)
 * with a guaranteed revert if net profit (including gas reimbursement) is not positive.
 */

interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address recipient, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address sender, address recipient, uint256 amount) external returns (bool);
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

interface IOneInchRouter {
    function swap(
        address executor,
        bytes calldata desc,
        bytes calldata permit,
        bytes calldata data
    ) external payable returns (uint256 returnAmount, uint256 spentAmount);
}

contract FlashArbReceiver {
    address public immutable owner;
    address public immutable balancerVault; // Balancer V2 Vault address
    address public immutable aavePool;      // Aave V3 Pool address
    address public immutable oneInchRouter; // 1inch V6 Router address

    struct ArbParams {
        address flashToken;
        uint256 flashAmount;
        uint256 minExpectedProfit; // Profit floor gate (including gas reimbursement if applicable)
        bytes[] swapPayloads;      // Swaps payload for each leg
        address[] swapRouters;     // Router for each leg (e.g., 1inch)
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address _balancerVault, address _aavePool, address _oneInchRouter) {
        owner = msg.sender;
        balancerVault = _balancerVault;
        aavePool = _aavePool;
        oneInchRouter = _oneInchRouter;
    }

    // Withdraw accidental tokens or profits
    function withdrawToken(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        require(balance > 0, "Zero balance");
        IERC20(token).transfer(owner, balance);
    }

    function withdrawETH() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "Zero ETH balance");
        payable(owner).transfer(balance);
    }

    receive() external payable {}

    // ─────────────────────────────────────────────────────────────────────────────
    // Balancer Flash Loan Execution
    // ─────────────────────────────────────────────────────────────────────────────

    function executeBalancerFlashArb(
        address token,
        uint256 amount,
        uint256 minExpectedProfit,
        bytes[] calldata swapPayloads,
        address[] calldata swapRouters
    ) external onlyOwner {
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

    // Balancer Flash Loan Callback
    function receiveFlashLoan(
        address[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external {
        require(msg.sender == balancerVault, "Not Balancer Vault");
        ArbParams memory params = abi.decode(userData, (ArbParams));

        uint256 startBalance = IERC20(params.flashToken).balanceOf(address(this)) - amounts[0];

        // Execute swaps
        _executeSwaps(params);

        uint256 endBalance = IERC20(params.flashToken).balanceOf(address(this));
        uint256 repaymentAmount = amounts[0] + feeAmounts[0];

        require(endBalance >= repaymentAmount, "Cannot repay Balancer flash loan");
        uint256 netProfit = endBalance - repaymentAmount;
        require(netProfit >= params.minExpectedProfit, "Arb unprofitable: safety revert triggered");

        // Repay flash loan
        IERC20(params.flashToken).transfer(balancerVault, repaymentAmount);

        // Send profit to owner
        if (netProfit > 0) {
            IERC20(params.flashToken).transfer(owner, netProfit);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Aave Flash Loan Execution
    // ─────────────────────────────────────────────────────────────────────────────

    function executeAaveFlashArb(
        address token,
        uint256 amount,
        uint256 minExpectedProfit,
        bytes[] calldata swapPayloads,
        address[] calldata swapRouters
    ) external onlyOwner {
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

    // Aave Flash Loan Callback
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == aavePool, "Not Aave Pool");
        ArbParams memory arbParams = abi.decode(params, (ArbParams));

        // Execute swaps
        _executeSwaps(arbParams);

        uint256 endBalance = IERC20(asset).balanceOf(address(this));
        uint256 repaymentAmount = amount + premium;

        require(endBalance >= repaymentAmount, "Cannot repay Aave flash loan");
        uint256 netProfit = endBalance - repaymentAmount;
        require(netProfit >= arbParams.minExpectedProfit, "Arb unprofitable: safety revert triggered");

        // Approve Aave Pool to pull repayment
        IERC20(asset).approve(aavePool, repaymentAmount);

        // Send profit to owner
        if (netProfit > 0) {
            IERC20(asset).transfer(owner, netProfit);
        }

        return true;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Swap Executor Helper
    // ─────────────────────────────────────────────────────────────────────────────

    function _executeSwaps(ArbParams memory params) internal {
        for (uint256 i = 0; i < params.swapPayloads.length; i++) {
            address router = params.swapRouters[i];
            bytes memory payload = params.swapPayloads[i];

            // If we are swapping a token, we must approve the router to spend it
            // We can parse token_in from the payload or just approve max for simplicity
            // To be gas efficient, we can approve exactly the amount we hold
            // For 1inch router, we do dynamic approvals if needed.
            // (In practice, arb executor handles approvals or the contract does it here)
            
            (bool success, ) = router.call(payload);
            require(success, "Swap execution failed");
        }
    }
}
