#!/usr/bin/env python3
"""
风控模块测试文件
测试OrderWindowTracker和PendingOrderTracker的功能
"""

import sys
from pathlib import Path

# 添加项目路径
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

# 直接导入模块，避免其他模块的导入错误
from quantsys.common.order_window_tracker import OrderWindowTracker
from quantsys.common.pending_order_tracker import OrderStatus, PendingOrderTracker
from quantsys.common.risk_manager import RiskManager


def test_order_window_tracker():
    """测试订单时间窗口跟踪器"""
    print("=" * 60)
    print("测试1: OrderWindowTracker - 订单拆分攻击防护")
    print("=" * 60)

    tracker = OrderWindowTracker(window_seconds=60, max_window_amount=1000.0)

    # 测试1: 正常订单
    allowed, total = tracker.add_order(100.0, "BTC-USDT", "buy")
    print(f"订单1: 金额=100 USDT, 允许={allowed}, 累计={total:.2f} USDT")
    assert allowed, "订单1应该被允许"

    # 测试2: 累计接近限制
    for i in range(8):
        allowed, total = tracker.add_order(100.0, "BTC-USDT", "buy")
        print(f"订单{i + 2}: 金额=100 USDT, 允许={allowed}, 累计={total:.2f} USDT")
        if i < 8:
            assert allowed, f"订单{i + 2}应该被允许"

    # 测试3: 超过限制
    allowed, total = tracker.add_order(100.0, "BTC-USDT", "buy")
    print(f"订单11: 金额=100 USDT, 允许={allowed}, 累计={total:.2f} USDT")
    assert not allowed, "订单11应该被拒绝（超过时间窗口限制）"

    # 测试4: 获取统计信息
    stats = tracker.get_stats()
    print(f"\n窗口统计: {stats}")

    print("\n✅ OrderWindowTracker测试通过\n")


def test_pending_order_tracker():
    """测试Pending订单跟踪器"""
    print("=" * 60)
    print("测试2: PendingOrderTracker - Pending订单跟踪")
    print("=" * 60)

    tracker = PendingOrderTracker()

    # 测试1: 添加订单
    result = tracker.add_order("order1", "BTC-USDT", "buy", 100.0, 50000.0)
    print(f"添加订单1: 结果={result}")
    assert result, "订单1应该成功添加"

    result = tracker.add_order("order2", "ETH-USDT", "buy", 50.0, 3000.0)
    print(f"添加订单2: 结果={result}")
    assert result, "订单2应该成功添加"

    # 测试2: 获取pending金额
    total_pending = tracker.get_total_pending_amount()
    buy_pending = tracker.get_total_pending_amount(side="buy")
    print(f"总pending金额: {total_pending:.2f} USDT")
    print(f"买入pending金额: {buy_pending:.2f} USDT")
    assert total_pending == 150.0, f"总pending金额应该是150.0，实际是{total_pending}"
    assert buy_pending == 150.0, f"买入pending金额应该是150.0，实际是{buy_pending}"

    # 测试3: 更新订单状态
    result = tracker.update_order_status("order1", OrderStatus.FILLED)
    print(f"更新订单1状态为FILLED: 结果={result}")
    assert result, "订单1状态应该成功更新"

    total_pending = tracker.get_total_pending_amount()
    print(f"更新后总pending金额: {total_pending:.2f} USDT")
    assert total_pending == 50.0, f"更新后总pending金额应该是50.0，实际是{total_pending}"

    # 测试4: 获取统计信息
    stats = tracker.get_stats()
    print(f"\nPending订单统计: {stats}")

    print("\n✅ PendingOrderTracker测试通过\n")


def test_risk_manager_integration():
    """测试RiskManager集成"""
    print("=" * 60)
    print("测试3: RiskManager集成测试")
    print("=" * 60)

    config = {
        "max_single_order_amount": 1000.0,
        "total_exposure_limit": 10.0,
        "order_window_seconds": 60,
        "max_window_amount": 2000.0,
    }
    risk_manager = RiskManager(config)

    # 测试1: 正常订单
    verdict = risk_manager.get_risk_verdict(
        symbol="BTC-USDT",
        side="buy",
        amount=0.1,
        price=50000.0,
        balance=10000.0,
        current_position=0.0,
        total_position=0.0,
        equity=10000.0,
        leverage=1.0,
        order_id="test_order_1",
    )
    print(f"订单1风险评估: 允许={verdict.allow_open}, 原因={verdict.blocked_reason}")
    assert verdict.allow_open, "订单1应该被允许"

    # 测试2: 检查pending跟踪器
    pending_amount = risk_manager.pending_order_tracker.get_total_pending_amount()
    print(f"Pending金额: {pending_amount:.2f} USDT")
    assert pending_amount > 0, "应该有pending订单"

    # 测试3: 检查时间窗口
    window_stats = risk_manager.order_window_tracker.get_stats()
    print(f"时间窗口统计: {window_stats}")

    print("\n✅ RiskManager集成测试通过\n")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("风控模块功能测试")
    print("=" * 60 + "\n")

    try:
        test_order_window_tracker()
        test_pending_order_tracker()
        test_risk_manager_integration()

        print("=" * 60)
        print("✅ 所有测试通过")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 未处理的异常: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
