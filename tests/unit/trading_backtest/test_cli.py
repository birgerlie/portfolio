import pytest
import json
import sys
from io import StringIO
from unittest.mock import patch
from trading_backtest.cli import main, format_result, cmd_analyze, cmd_status


def test_cli_status_command():
    """Test status command returns 0."""
    with patch.object(sys, 'argv', ['cli.py', 'status']):
        result = main()
        assert result == 0


def test_analyze_command_with_valid_input(capsys):
    """Test analyze command with valid market and belief data."""
    with patch.object(sys, 'argv', [
        'cli.py', 'analyze',
        '--market', '{"avg_return": 0.15, "volatility": 0.15, "positive_pct": 0.75, "momentum": 0.20}',
        '--beliefs', '{"NVDA": ["high_growth", 0.88], "AVGO": ["high_growth", 0.85]}',
        '--format', 'json'
    ]):
        result = main()
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output['market']['regime'] == 'BULL'
        assert output['strategy']['selected'] == 'kelly_monthly_rebalance'
        assert len(output['portfolio']['allocations']) == 2


def test_analyze_command_with_missing_beliefs():
    """Test that analyze command requires beliefs argument."""
    with patch.object(sys, 'argv', [
        'cli.py', 'analyze',
        '--market', '{"avg_return": 0.15, "volatility": 0.15, "positive_pct": 0.75, "momentum": 0.20}'
    ]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        # argparse exits with status 2 for missing required arguments
        assert exc_info.value.code == 2


def test_format_result_structure():
    """Test that format_result produces correct structure."""
    from trading_backtest.automation_controller import AutonomousController

    controller = AutonomousController()
    result = controller.analyze(
        market_metrics={'avg_return': 0.15, 'volatility': 0.15, 'positive_pct': 0.75, 'momentum': 0.20},
        beliefs_dict={'NVDA': ('high_growth', 0.88)}
    )

    formatted = format_result(result)

    # Verify structure
    assert 'market' in formatted
    assert 'strategy' in formatted
    assert 'portfolio' in formatted
    assert 'execution' in formatted
    assert 'overall_confidence' in formatted

    # Verify market section
    assert formatted['market']['regime'] in ['BULL', 'BEAR', 'TRANSITION', 'CONSOLIDATION']

    # Verify strategy section
    assert 'selected' in formatted['strategy']
    assert 'score' in formatted['strategy']

    # Verify portfolio section
    assert 'allocations' in formatted['portfolio']
    assert len(formatted['portfolio']['allocations']) > 0

    # Verify execution section
    assert 'trades' in formatted['execution']
    assert 'total_trades' in formatted['execution']
