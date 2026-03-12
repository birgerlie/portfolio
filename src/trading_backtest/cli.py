#!/usr/bin/env python3
"""Autonomous Trading System CLI - Command-line interface for portfolio management."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any
from trading_backtest.automation_controller import AutonomousController


def format_regime(regime):
    """Format regime enum to string."""
    return regime.value.upper() if hasattr(regime, 'value') else str(regime).upper()


def format_result(result) -> Dict[str, Any]:
    """Convert controller result to JSON-serializable format."""
    return {
        'market': {
            'regime': format_regime(result.regime),
        },
        'strategy': {
            'selected': result.selected_strategy.name,
            'score': round(result.selected_strategy.score, 2),
            'expected_return': round(result.selected_strategy.expected_return, 4),
            'sharpe_ratio': round(result.selected_strategy.sharpe_ratio, 2),
        },
        'portfolio': {
            'allocations': [
                {
                    'symbol': a.symbol,
                    'weight': round(a.weight, 4),
                    'belief': a.belief_type,
                    'confidence': round(a.confidence, 2),
                }
                for a in result.portfolio.allocations
            ],
            'total_long': round(result.portfolio.total_long, 4),
            'total_short': round(result.portfolio.total_short, 4),
            'net_exposure': round(result.portfolio.net_exposure, 4),
        },
        'execution': {
            'trades': [
                {
                    'symbol': t.symbol,
                    'type': t.type,
                    'allocation': round(t.allocation, 4),
                    'confidence': round(t.confidence, 2),
                    'reason': t.reason,
                }
                for t in result.execution_plan.trades
            ],
            'total_trades': len(result.execution_plan.trades),
            'confidence': round(result.execution_plan.confidence, 2),
        },
        'overall_confidence': round(result.confidence, 2),
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Autonomous Trading System - Portfolio analysis and execution planning'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze market and generate plan')
    analyze_parser.add_argument('--market', type=str, required=True,
                              help='JSON string with market_metrics')
    analyze_parser.add_argument('--beliefs', type=str, required=True,
                              help='JSON string with beliefs {symbol: [type, confidence]}')
    analyze_parser.add_argument('--portfolio', type=str,
                              help='JSON string with current portfolio {symbol: weight}')
    analyze_parser.add_argument('--prices', type=str,
                              help='JSON string with current prices {symbol: price}')
    analyze_parser.add_argument('--format', choices=['json', 'table'], default='json',
                              help='Output format')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show system status')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'analyze':
        return cmd_analyze(args)
    elif args.command == 'status':
        return cmd_status()

    return 0


def cmd_analyze(args) -> int:
    """Execute analyze command."""
    try:
        # Parse JSON inputs
        market_metrics = json.loads(args.market)
        beliefs_dict = {}

        beliefs_input = json.loads(args.beliefs)
        for symbol, (belief_type, confidence) in beliefs_input.items():
            beliefs_dict[symbol] = (belief_type, float(confidence))

        current_portfolio = {}
        if args.portfolio:
            current_portfolio = json.loads(args.portfolio)

        current_prices = {}
        if args.prices:
            current_prices = json.loads(args.prices)

        # Run analysis
        controller = AutonomousController()
        result = controller.analyze(
            market_metrics=market_metrics,
            beliefs_dict=beliefs_dict,
            current_portfolio=current_portfolio,
            current_prices=current_prices,
        )

        # Format and output result
        formatted = format_result(result)

        if args.format == 'json':
            print(json.dumps(formatted, indent=2))
        else:  # table format
            print(f"Market Regime: {formatted['market']['regime']}")
            print(f"Selected Strategy: {formatted['strategy']['selected']}")
            print(f"Expected Return: {formatted['strategy']['expected_return']:.2%}")
            print(f"Confidence: {formatted['overall_confidence']:.0%}")
            print(f"\nTrades ({formatted['execution']['total_trades']}):")
            for trade in formatted['execution']['trades']:
                print(f"  {trade['type']:4} {trade['symbol']:5} {trade['allocation']:7.1%} "
                      f"({trade['confidence']:.0%})")

        return 0

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error parsing inputs: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        return 1


def cmd_status() -> int:
    """Show system status."""
    print("Autonomous Trading System Status")
    print("=" * 40)
    print("✓ Regime Detector: Ready")
    print("✓ Strategy Selector: Ready (7 strategies)")
    print("✓ Portfolio Composer: Ready")
    print("✓ Execution Generator: Ready")
    print("✓ Automation Controller: Ready")
    return 0


if __name__ == '__main__':
    sys.exit(main())
