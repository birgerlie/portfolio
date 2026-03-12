"""Unit ledger — subscriptions, redemptions, lock-up enforcement."""

from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
from typing import List
from fund.types import Fund, Member, Transaction, TransactionType, TransactionStatus, FeeBreakdown


class UnitLedger:
    def __init__(self):
        self._transactions: List[Transaction] = []

    def subscribe(self, fund: Fund, member: Member, amount: Decimal,
                  process_date: date) -> Transaction:
        nav_per_unit = fund.nav_per_unit
        units = (amount / nav_per_unit).quantize(Decimal("1"), rounding=ROUND_DOWN)
        member.units += units
        member.cost_basis += amount
        fund.units_outstanding += units
        fund.nav += amount
        tx = Transaction(
            member_id=member.id, type=TransactionType.SUBSCRIBE,
            units=units, nav_per_unit=nav_per_unit, amount=amount,
            fee_breakdown=FeeBreakdown(),
            timestamp=datetime.combine(process_date, datetime.min.time()),
            status=TransactionStatus.PROCESSED)
        self._transactions.append(tx)
        return tx

    def redeem(self, fund: Fund, member: Member, units: Decimal,
               process_date: date) -> Transaction:
        nav_per_unit = fund.nav_per_unit
        payout = units * nav_per_unit

        # Check lock-up
        if process_date < member.lock_up_until:
            tx = Transaction(
                member_id=member.id, type=TransactionType.REDEEM,
                units=units, nav_per_unit=nav_per_unit, amount=payout,
                fee_breakdown=FeeBreakdown(),
                timestamp=datetime.combine(process_date, datetime.min.time()),
                status=TransactionStatus.REJECTED)
            self._transactions.append(tx)
            return tx

        # Check sufficient units
        if units > member.units:
            tx = Transaction(
                member_id=member.id, type=TransactionType.REDEEM,
                units=units, nav_per_unit=nav_per_unit, amount=payout,
                fee_breakdown=FeeBreakdown(),
                timestamp=datetime.combine(process_date, datetime.min.time()),
                status=TransactionStatus.REJECTED)
            self._transactions.append(tx)
            return tx

        # Process
        member.units -= units
        fund.units_outstanding -= units
        fund.nav -= payout
        tx = Transaction(
            member_id=member.id, type=TransactionType.REDEEM,
            units=units, nav_per_unit=nav_per_unit, amount=payout,
            fee_breakdown=FeeBreakdown(),
            timestamp=datetime.combine(process_date, datetime.min.time()),
            status=TransactionStatus.PROCESSED)
        self._transactions.append(tx)
        return tx

    def get_history(self, member_id: str) -> List[Transaction]:
        return [tx for tx in self._transactions if tx.member_id == member_id]
