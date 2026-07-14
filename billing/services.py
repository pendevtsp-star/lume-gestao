from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from billing.models import CashClosing, Charge, Expense, Membership, Payment, add_months


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class MembershipReceivable:
    """Uma mensalidade ainda sem lancamento financeiro materializado."""

    membership: Membership
    reference_month: date
    due_date: date
    amount: Decimal

    @property
    def patient_display(self):
        return self.membership.patient.full_name

    @property
    def item_display(self):
        return f"Mensalidade - {self.membership.plan.name}"

    @property
    def status(self):
        return Payment.Status.OVERDUE if self.due_date < timezone.localdate() else Payment.Status.PENDING

    @property
    def effective_status(self):
        return self.status

    def get_status_display(self):
        return "Vencido" if self.status == Payment.Status.OVERDUE else "Pendente"

    @property
    def effective_status_display(self):
        return self.get_status_display()

    @property
    def days_overdue(self):
        if self.status != Payment.Status.OVERDUE:
            return 0
        return max((timezone.localdate() - self.due_date).days, 0)


def month_start(day):
    return day.replace(day=1)


def cycle_due_date(membership, reference_month):
    return reference_month.replace(day=min(membership.due_day, 28))


def get_or_create_membership_payment(membership, reference_month):
    reference_month = month_start(reference_month)
    payment = Payment.objects.filter(membership=membership, reference_month=reference_month).first()
    if payment:
        return payment, False
    payment = Payment(
        patient=membership.patient,
        membership=membership,
        item_type=Payment.ItemType.MEMBERSHIP,
        description=membership.plan.name,
        reference_month=reference_month,
        due_date=cycle_due_date(membership, reference_month),
        amount=membership.monthly_amount,
        status=Payment.Status.PENDING,
        method=Payment.Method.MANUAL,
    )
    payment.full_clean()
    payment.save()
    return payment, True


def receive_membership_month(*, membership, reference_month, method, paid_at=None, notes=""):
    paid_at = paid_at or timezone.localdate()
    payment, _created = get_or_create_membership_payment(membership, reference_month)
    if payment.status == Payment.Status.PAID:
        return payment
    payment.patient = membership.patient
    payment.item_type = Payment.ItemType.MEMBERSHIP
    payment.description = payment.description or membership.plan.name
    payment.amount = membership.monthly_amount
    payment.method = method
    payment.status = Payment.Status.PAID
    payment.paid_at = paid_at
    payment.due_date = payment.due_date or cycle_due_date(membership, month_start(reference_month))
    notes = (notes or "").strip()
    if notes:
        payment.notes = f"{payment.notes}\n{notes}".strip() if payment.notes else notes
    payment.full_clean()
    payment.save()
    return payment


def membership_receivables_between(starts_on, ends_on, query="", limit=None):
    """Lista mensalidades ativas sem Payment dentro do intervalo de vencimento.

    O recebimento rapido cria o Payment apenas quando a gestora registra o
    pagamento. Esta funcao evita que essa decisao esconda a cobranca do painel
    e das automacoes antes do recebimento.
    """
    if ends_on < starts_on:
        return []

    first_month = month_start(starts_on)
    last_month = month_start(ends_on)
    memberships = Membership.objects.select_related("patient", "plan").filter(status=Membership.Status.ACTIVE)
    query = (query or "").strip()
    if query:
        memberships = memberships.filter(
            Q(patient__full_name__icontains=query)
            | Q(patient__phone__icontains=query)
            | Q(patient__cpf__icontains=query)
            | Q(plan__name__icontains=query)
        )

    memberships = list(memberships.order_by("patient__full_name", "plan__name"))
    membership_ids = [membership.pk for membership in memberships]
    existing_pairs = set(
        Payment.objects.filter(
            membership_id__in=membership_ids,
            reference_month__gte=first_month,
            reference_month__lte=last_month,
        ).values_list("membership_id", "reference_month")
    )

    rows = []
    reference_month = first_month
    while reference_month <= last_month:
        for membership in memberships:
            # Do not infer debt for a cycle before the patient joined the plan.
            if reference_month < month_start(membership.start_date):
                continue
            if (membership.pk, reference_month) in existing_pairs:
                continue
            if membership.monthly_amount <= ZERO:
                continue
            due_date = cycle_due_date(membership, reference_month)
            if starts_on <= due_date <= ends_on:
                rows.append(
                    MembershipReceivable(
                        membership=membership,
                        reference_month=reference_month,
                        due_date=due_date,
                        amount=membership.monthly_amount,
                    )
                )
        reference_month = add_months(reference_month, 1)

    rows.sort(key=lambda row: (row.due_date, row.patient_display, row.item_display))
    return rows[:limit] if limit else rows


def open_membership_receivables(query="", months_back=2, months_ahead=2, limit=72):
    """Return the actionable window for the finance work queue.

    We intentionally limit the historical look-back. Older cycles can predate
    Lume and should be reviewed by the clinic instead of being inferred as debt.
    """
    today = timezone.localdate()
    starts_on = add_months(month_start(today), -months_back)
    ends_on = add_months(month_start(today), months_ahead).replace(day=28)
    return membership_receivables_between(
        starts_on,
        ends_on,
        query=query,
        limit=limit,
    )


def upcoming_membership_receivables(query="", months_ahead=6):
    today = timezone.localdate()
    last_month = add_months(month_start(today), months_ahead)
    rows = membership_receivables_between(month_start(today), last_month.replace(day=28), query=query)
    next_rows = {}
    for row in rows:
        next_rows.setdefault(row.membership.pk, row)
    return [
        {
            "membership": row.membership,
            "reference_month": row.reference_month,
            "due_date": row.due_date,
            "amount": row.amount,
        }
        for row in list(next_rows.values())[:24]
    ]


def sum_amount(queryset):
    return queryset.aggregate(total=Sum("amount"))["total"] or ZERO


def cash_summary_for_date(day=None):
    day = day or timezone.localdate()
    payments = Payment.objects.filter(status=Payment.Status.PAID, paid_at=day).select_related(
        "patient", "membership__patient", "membership__plan"
    )
    charges = Charge.objects.filter(status=Charge.Status.RECEIVED, received_at=day).select_related("patient")
    expenses = Expense.objects.filter(status=Expense.Status.PAID, paid_at=day).select_related("category")
    method_rows = []
    for method, label in Payment.Method.choices:
        total = sum_amount(payments.filter(method=method))
        if total:
            method_rows.append({"method": method, "label": label, "total": total, "count": payments.filter(method=method).count()})
    payments_total = sum_amount(payments)
    charges_total = sum_amount(charges)
    expenses_total = sum_amount(expenses)
    cash_expected = sum_amount(payments.filter(method=Payment.Method.CASH))
    closing = CashClosing.objects.filter(date=day).select_related("closed_by").first()
    return {
        "date": day,
        "payments": payments.order_by("-paid_at", "patient__full_name", "membership__patient__full_name"),
        "charges": charges.order_by("patient__full_name", "description"),
        "expenses": expenses.order_by("category__name", "description"),
        "method_rows": method_rows,
        "payments_total": payments_total,
        "charges_total": charges_total,
        "revenue_total": payments_total + charges_total,
        "expenses_total": expenses_total,
        "net_total": payments_total + charges_total - expenses_total,
        "cash_expected": cash_expected,
        "closing": closing,
    }


def close_cash_for_date(*, day, user, cash_counted=None, notes=""):
    summary = cash_summary_for_date(day)
    closing, _created = CashClosing.objects.get_or_create(date=day)
    closing.payments_total = summary["payments_total"]
    closing.charges_total = summary["charges_total"]
    closing.expenses_total = summary["expenses_total"]
    closing.cash_expected = summary["cash_expected"]
    closing.cash_counted = cash_counted
    closing.notes = notes
    closing.closed_by = user
    closing.closed_at = timezone.now()
    closing.full_clean()
    closing.save()
    return closing
