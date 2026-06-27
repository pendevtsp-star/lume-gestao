from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, TemplateView, View

from accounts.models import UserProfile
from accounts.permissions import ManagementAccessMixin, RoleRequiredMixin
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.exports import br_currency, pdf_response, xlsx_response
from core.models import AuditLog
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment
from team.models import Professional


ZERO = Decimal("0.00")
ONE_DECIMAL = Decimal("0.1")


def as_decimal(value):
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def sum_total(queryset, field="amount"):
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def percent(value, total):
    total_decimal = as_decimal(total)
    if total_decimal <= 0:
        return ZERO
    return (as_decimal(value) * Decimal("100") / total_decimal).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def percent_int(value, total):
    return int(percent(value, total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if total else 0


def shift_month(day, delta):
    month_index = day.month - 1 + delta
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def month_last_day(day):
    return date(day.year, day.month, monthrange(day.year, day.month)[1])


def coerce_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def prettify_value(value):
    if value in (None, ""):
        return "-"
    if isinstance(value, bool):
        return "Sim" if value else "Nao"
    if isinstance(value, list):
        rendered = ", ".join(prettify_value(item) for item in value if item not in (None, ""))
        return rendered or "-"
    if isinstance(value, dict):
        rendered = ", ".join(f"{key}: {prettify_value(item)}" for key, item in value.items())
        return rendered or "-"
    return str(value)


def br_percent(value):
    return f"{value}%".replace(".", ",")


def br_date(value):
    if isinstance(value, str):
        parsed = coerce_date(value)
        if parsed:
            return parsed.strftime("%d/%m/%Y")
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else str(value)


def user_can_access_audit(user):
    profile = getattr(user, "profile", None)
    return bool(user.is_superuser or (profile and profile.role == UserProfile.Role.MANAGEMENT))


class PeriodReportMixin:
    default_preset = "current_month"
    preset_choices = [
        ("current_month", "Mes atual"),
        ("last_month", "Mes anterior"),
        ("current_quarter", "Trimestre atual"),
        ("last_90_days", "Ultimos 90 dias"),
        ("current_year", "Ano atual"),
        ("custom", "Periodo personalizado"),
    ]

    def resolve_preset(self, preset, today):
        if preset == "last_month":
            end = shift_month(today.replace(day=1), 0) - timedelta(days=1)
            return end.replace(day=1), end
        if preset == "current_quarter":
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            return date(today.year, quarter_month, 1), today
        if preset == "last_90_days":
            return today - timedelta(days=89), today
        if preset == "current_year":
            return date(today.year, 1, 1), today
        return today.replace(day=1), today

    def get_period(self):
        today = timezone.localdate()
        preset = (self.request.GET.get("preset") or self.default_preset).strip()
        raw_start = (self.request.GET.get("start") or "").strip()
        raw_end = (self.request.GET.get("end") or "").strip()

        if preset == "custom":
            start = coerce_date(raw_start)
            end = coerce_date(raw_end)
            fallback_start, fallback_end = self.resolve_preset(self.default_preset, today)
            start = start or fallback_start
            end = end or fallback_end
        else:
            start, end = self.resolve_preset(preset, today)

        if start > end:
            start, end = end, start

        return {
            "preset": preset,
            "start": start,
            "end": end,
            "start_iso": start.isoformat(),
            "end_iso": end.isoformat(),
            "preset_choices": self.preset_choices,
        }

    def get_period_context(self):
        period = self.get_period()
        return {
            "preset": period["preset"],
            "start": period["start_iso"],
            "end": period["end_iso"],
            "preset_choices": period["preset_choices"],
        }


class ReportsDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    template_name = "reports/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_start = today.replace(day=1)

        payments = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=month_start, paid_at__lte=today)
        charges = Charge.objects.filter(
            status=Charge.Status.RECEIVED,
            received_at__gte=month_start,
            received_at__lte=today,
        )
        expenses = Expense.objects.exclude(status=Expense.Status.CANCELED).filter(
            due_date__gte=month_start,
            due_date__lte=today,
        )
        appointments = Appointment.objects.filter(
            starts_at__date__gte=month_start,
            starts_at__date__lte=today,
            status=Appointment.Status.COMPLETED,
        )

        revenue_total = sum_total(payments) + sum_total(charges)
        expense_total = sum_total(expenses)
        net_total = revenue_total - expense_total
        active_patients = Patient.objects.filter(active=True).count()
        active_memberships = Membership.objects.filter(status=Membership.Status.ACTIVE).count()
        audit_total = AuditLog.objects.count()

        context.update(
            {
                "report_section": "overview",
                "can_access_audit": user_can_access_audit(self.request.user),
                "overview_cards": [
                    {
                        "title": "Financeiro",
                        "description": "Receita, despesas, resultado, saude financeira e contas em aberto.",
                        "url_name": "reports:financial",
                        "metric_label": "Resultado do mes",
                        "metric_value": f"R$ {net_total:.2f}",
                    },
                    {
                        "title": "Gestao de adesao",
                        "description": "Adesoes, atendimentos, pacientes ativos e comportamento operacional.",
                        "url_name": "reports:clinic",
                        "metric_label": "Atendimentos realizados",
                        "metric_value": appointments.count(),
                    },
                    {
                        "title": "Auditoria",
                        "description": "Historico de alteracoes, usuarios, objetos e rastreabilidade.",
                        "url_name": "reports:audit",
                        "metric_label": "Eventos registrados",
                        "metric_value": audit_total,
                        "restricted": True,
                    },
                ],
                "overview_metrics": {
                    "revenue_total": revenue_total,
                    "expense_total": expense_total,
                    "net_total": net_total,
                    "active_patients": active_patients,
                    "active_memberships": active_memberships,
                },
            }
        )
        return context


class FinancialReportView(PeriodReportMixin, RoleRequiredMixin, TemplateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    template_name = "reports/financial_report.html"

    def get_filters(self):
        return {
            "method": (self.request.GET.get("method") or "").strip(),
            "kind": (self.request.GET.get("kind") or "").strip(),
            "category": (self.request.GET.get("category") or "").strip(),
            "plan": (self.request.GET.get("plan") or "").strip(),
            "include_charges": (self.request.GET.get("include_charges") or "1").strip() != "0",
        }

    def build_money_breakdown(self, rows, total, label_key, value_key, count_key=None):
        items = []
        for row in rows:
            label = row[label_key] or "Sem classificacao"
            value = row[value_key] or ZERO
            items.append(
                {
                    "label": label,
                    "value": value,
                    "count": row.get(count_key) if count_key else None,
                    "percentage": percent_int(value, total),
                }
            )
        return items

    def get_report_data(self):
        period = self.get_period()
        filters = self.get_filters()
        start = period["start"]
        end = period["end"]
        today = timezone.localdate()

        paid_payments = Payment.objects.filter(
            status=Payment.Status.PAID,
            paid_at__gte=start,
            paid_at__lte=end,
        ).select_related("membership__patient", "membership__plan")
        pending_payments = Payment.objects.filter(
            status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            due_date__gte=start,
            due_date__lte=end,
        ).select_related("membership__patient", "membership__plan")
        if filters["method"]:
            paid_payments = paid_payments.filter(method=filters["method"])
        if filters["plan"]:
            paid_payments = paid_payments.filter(membership__plan_id=filters["plan"])
            pending_payments = pending_payments.filter(membership__plan_id=filters["plan"])

        received_charges = Charge.objects.none()
        pending_charges = Charge.objects.none()
        if filters["include_charges"]:
            received_charges = Charge.objects.filter(
                status=Charge.Status.RECEIVED,
                received_at__gte=start,
                received_at__lte=end,
            ).select_related("patient")
            pending_charges = Charge.objects.filter(
                status__in=[Charge.Status.OPEN, Charge.Status.OVERDUE],
                due_date__gte=start,
                due_date__lte=end,
            ).select_related("patient")

        expenses = Expense.objects.exclude(status=Expense.Status.CANCELED).filter(
            due_date__gte=start,
            due_date__lte=end,
        ).select_related("category")
        if filters["kind"]:
            expenses = expenses.filter(kind=filters["kind"])
        if filters["category"]:
            expenses = expenses.filter(category_id=filters["category"])

        revenue_total = sum_total(paid_payments) + sum_total(received_charges)
        expense_total = sum_total(expenses)
        paid_expense_total = sum_total(expenses.filter(status=Expense.Status.PAID))
        open_expense_total = sum_total(expenses.filter(status=Expense.Status.OPEN))
        net_result = revenue_total - expense_total
        pending_total = sum_total(pending_payments) + sum_total(pending_charges)
        overdue_payments = pending_payments.filter(Q(status=Payment.Status.OVERDUE) | Q(due_date__lt=today))
        overdue_charges = pending_charges.filter(Q(status=Charge.Status.OVERDUE) | Q(due_date__lt=today))
        overdue_total = sum_total(overdue_payments) + sum_total(overdue_charges)
        margin = percent(net_result, revenue_total)
        expense_ratio = percent(expense_total, revenue_total)
        overdue_ratio = percent(overdue_total, pending_total)

        if revenue_total <= 0 and expense_total <= 0:
            health_label = "Sem dados suficientes"
            health_tone = "neutral"
            health_summary = "Ainda nao ha movimentacao relevante no periodo selecionado."
        elif net_result >= 0 and overdue_ratio <= Decimal("15.0") and expense_ratio <= Decimal("80.0"):
            health_label = "Saudavel"
            health_tone = "success"
            health_summary = "A operacao esta gerando caixa e com baixa pressao de inadimplencia."
        elif net_result >= 0 and overdue_ratio <= Decimal("30.0") and expense_ratio <= Decimal("100.0"):
            health_label = "Em atencao"
            health_tone = "warning"
            health_summary = "A clinica segue positiva, mas merece acompanhar despesas e contas vencidas."
        else:
            health_label = "Critica"
            health_tone = "danger"
            health_summary = "Receita, despesas ou inadimplencia indicam necessidade de acao imediata."

        flow = defaultdict(lambda: {"month": None, "revenue": ZERO, "expenses": ZERO})
        for row in paid_payments.annotate(month=TruncMonth("paid_at")).values("month").annotate(total=Sum("amount")):
            flow[row["month"]]["month"] = row["month"]
            flow[row["month"]]["revenue"] += row["total"] or ZERO
        for row in received_charges.annotate(month=TruncMonth("received_at")).values("month").annotate(total=Sum("amount")):
            flow[row["month"]]["month"] = row["month"]
            flow[row["month"]]["revenue"] += row["total"] or ZERO
        for row in expenses.annotate(month=TruncMonth("due_date")).values("month").annotate(total=Sum("amount")):
            flow[row["month"]]["month"] = row["month"]
            flow[row["month"]]["expenses"] += row["total"] or ZERO

        monthly_flow = []
        for row in sorted(flow.values(), key=lambda item: item["month"]):
            monthly_flow.append(
                {
                    "month": row["month"],
                    "revenue": row["revenue"],
                    "expenses": row["expenses"],
                    "net": row["revenue"] - row["expenses"],
                    "margin": percent(row["revenue"] - row["expenses"], row["revenue"]),
                }
            )

        revenue_by_source_rows = list(
            paid_payments.values("method")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total", "method")
        )
        revenue_by_source = self.build_money_breakdown(
            [
                {
                    "source_label": dict(Payment.Method.choices).get(row["method"], row["method"]),
                    "total": row["total"],
                    "count": row["count"],
                }
                for row in revenue_by_source_rows
            ],
            revenue_total,
            "source_label",
            "total",
            "count",
        )
        charge_received_total = sum_total(received_charges)
        if charge_received_total > 0:
            revenue_by_source.append(
                {
                    "label": "Cobrancas avulsas",
                    "value": charge_received_total,
                    "count": received_charges.count(),
                    "percentage": percent_int(charge_received_total, revenue_total),
                }
            )

        expenses_by_category_rows = list(
            expenses.values("category__name", "kind")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total", "category__name")
        )
        expenses_by_category = self.build_money_breakdown(
            [
                {
                    "category_label": row["category__name"] or f"Sem categoria ({row['kind']})",
                    "total": row["total"],
                    "count": row["count"],
                }
                for row in expenses_by_category_rows
            ],
            expense_total,
            "category_label",
            "total",
            "count",
        )

        revenue_by_plan_rows = list(
            paid_payments.values("membership__plan__name")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total", "membership__plan__name")[:8]
        )
        revenue_by_plan = self.build_money_breakdown(
            [
                {
                    "plan_label": row["membership__plan__name"] or "Sem plano",
                    "total": row["total"],
                    "count": row["count"],
                }
                for row in revenue_by_plan_rows
            ],
            revenue_total,
            "plan_label",
            "total",
            "count",
        )

        receivable_alerts = [
            {
                "type": "Mensalidade",
                "patient": payment.membership.patient.full_name,
                "description": payment.membership.plan.name,
                "due_date": payment.due_date,
                "status": "Vencido" if payment.due_date < today else payment.get_status_display(),
                "amount": payment.amount,
            }
            for payment in pending_payments.order_by("due_date")[:6]
        ]
        receivable_alerts.extend(
            [
                {
                    "type": "Cobranca",
                    "patient": charge.patient.full_name if charge.patient else "Sem paciente",
                    "description": charge.description,
                    "due_date": charge.due_date,
                    "status": "Vencida" if charge.due_date < today else charge.get_status_display(),
                    "amount": charge.amount,
                }
                for charge in pending_charges.order_by("due_date")[:6]
            ]
        )
        receivable_alerts = sorted(receivable_alerts, key=lambda row: row["due_date"])[:10]

        return {
            "report_section": "financial",
            "can_access_audit": user_can_access_audit(self.request.user),
            **self.get_period_context(),
            "selected_method": filters["method"],
            "selected_kind": filters["kind"],
            "selected_category": filters["category"],
            "selected_plan": filters["plan"],
            "include_charges": filters["include_charges"],
            "method_choices": Payment.Method.choices,
            "kind_choices": Expense.Kind.choices,
            "category_choices": ExpenseCategory.objects.filter(active=True).order_by("name"),
            "plan_choices": ServicePlan.objects.filter(active=True).order_by("name"),
            "revenue_total": revenue_total,
            "charge_revenue_total": charge_received_total,
            "expense_total": expense_total,
            "paid_expense_total": paid_expense_total,
            "open_expense_total": open_expense_total,
            "net_result": net_result,
            "pending_total": pending_total,
            "overdue_total": overdue_total,
            "margin": margin,
            "expense_ratio": expense_ratio,
            "overdue_ratio": overdue_ratio,
            "health_label": health_label,
            "health_tone": health_tone,
            "health_summary": health_summary,
            "monthly_flow": monthly_flow,
            "revenue_by_source": revenue_by_source,
            "expenses_by_category": expenses_by_category,
            "revenue_by_plan": revenue_by_plan,
            "receivable_alerts": receivable_alerts,
            "payments_count": paid_payments.count(),
            "received_charges_count": received_charges.count(),
            "expenses_count": expenses.count(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_report_data())
        return context


class FinancialReportExportView(FinancialReportView, View):
    def get(self, request, *args, **kwargs):
        data = self.get_report_data()
        if kwargs["export_format"] == "xlsx":
            return self.export_xlsx(data)
        return self.export_pdf(data)

    def summary_rows(self, data):
        return [
            ("Periodo", f"{data['start']} a {data['end']}"),
            ("Receita total", data["revenue_total"]),
            ("Receita por cobrancas avulsas", data["charge_revenue_total"]),
            ("Despesa total", data["expense_total"]),
            ("Despesas pagas", data["paid_expense_total"]),
            ("Despesas em aberto", data["open_expense_total"]),
            ("Resultado do periodo", data["net_result"]),
            ("Margem", f"{data['margin']}%"),
            ("Contas a receber", data["pending_total"]),
            ("Contas vencidas", data["overdue_total"]),
            ("Saude financeira", data["health_label"]),
        ]

    def export_xlsx(self, data):
        sheets = [
            ("Resumo financeiro", ["Indicador", "Valor"], self.summary_rows(data)),
            (
                "Fluxo mensal",
                ["Mes", "Receita", "Despesa", "Resultado", "Margem"],
                [
                    (
                        row["month"].strftime("%m/%Y"),
                        row["revenue"],
                        row["expenses"],
                        row["net"],
                        f"{row['margin']}%",
                    )
                    for row in data["monthly_flow"]
                ],
            ),
            (
                "Receita por origem",
                ["Origem", "Lancamentos", "Percentual", "Total"],
                [
                    (row["label"], row["count"] or "-", f"{row['percentage']}%", row["value"])
                    for row in data["revenue_by_source"]
                ],
            ),
            (
                "Despesas por categoria",
                ["Categoria", "Lancamentos", "Percentual", "Total"],
                [
                    (row["label"], row["count"] or "-", f"{row['percentage']}%", row["value"])
                    for row in data["expenses_by_category"]
                ],
            ),
            (
                "Receita por plano",
                ["Plano", "Recebimentos", "Percentual", "Total"],
                [
                    (row["label"], row["count"] or "-", f"{row['percentage']}%", row["value"])
                    for row in data["revenue_by_plan"]
                ],
            ),
            (
                "Recebiveis",
                ["Tipo", "Paciente", "Descricao", "Vencimento", "Status", "Valor"],
                [
                    (
                        row["type"],
                        row["patient"],
                        row["description"],
                        row["due_date"].strftime("%d/%m/%Y"),
                        row["status"],
                        row["amount"],
                    )
                    for row in data["receivable_alerts"]
                ],
            ),
        ]
        return xlsx_response("relatorio_financeiro_lume.xlsx", sheets)

    def export_pdf(self, data):
        money_labels = {
            "Receita total",
            "Receita por cobrancas avulsas",
            "Despesa total",
            "Despesas pagas",
            "Despesas em aberto",
            "Resultado do periodo",
            "Contas a receber",
            "Contas vencidas",
        }
        summary_lines = [
            f"{label}: {br_currency(value) if label in money_labels else br_percent(value) if label == 'Margem' else value}"
            for label, value in self.summary_rows(data)
        ]
        if summary_lines:
            summary_lines[0] = f"Periodo: {br_date(data['start'])} a {br_date(data['end'])}"
        sections = [
            ("Resumo financeiro", summary_lines),
            ("Leitura rapida", [data["health_summary"]]),
        ]
        charts = [
            {
                "title": "Receita x despesa por mes",
                "rows": [
                    {
                        "label": row["month"].strftime("%m/%Y"),
                        "value": row["net"],
                        "display": f"Resultado {br_currency(row['net'])}",
                        "color": "#60724F" if row["net"] >= 0 else "#B06B3A",
                    }
                    for row in data["monthly_flow"]
                ],
            },
            {
                "title": "Principais receitas",
                "rows": [
                    {"label": row["label"], "value": row["value"], "display": br_currency(row["value"])}
                    for row in data["revenue_by_source"]
                    if row["value"]
                ],
            },
            {
                "title": "Principais despesas",
                "rows": [
                    {
                        "label": row["label"],
                        "value": row["value"],
                        "display": br_currency(row["value"]),
                        "color": "#B06B3A",
                    }
                    for row in data["expenses_by_category"]
                    if row["value"]
                ],
            },
        ]
        tables = [
            (
                "Fluxo mensal",
                ["Mes", "Receita", "Despesa", "Resultado", "Margem"],
                [
                    (
                        row["month"].strftime("%m/%Y"),
                        br_currency(row["revenue"]),
                        br_currency(row["expenses"]),
                        br_currency(row["net"]),
                        br_percent(row["margin"]),
                    )
                    for row in data["monthly_flow"]
                ],
            ),
            (
                "Receita por origem",
                ["Origem", "Lancamentos", "Percentual", "Total"],
                [
                    (row["label"], row["count"] or "-", br_percent(row["percentage"]), br_currency(row["value"]))
                    for row in data["revenue_by_source"]
                ],
            ),
            (
                "Despesas por categoria",
                ["Categoria", "Lancamentos", "Percentual", "Total"],
                [
                    (row["label"], row["count"] or "-", br_percent(row["percentage"]), br_currency(row["value"]))
                    for row in data["expenses_by_category"]
                ],
            ),
        ]
        return pdf_response(
            "relatorio_financeiro_lume.pdf",
            "Relatorio financeiro - Lume",
            sections=sections,
            charts=charts,
            tables=tables,
            landscape_page=True,
            disposition="inline" if self.request.GET.get("inline") == "1" else "attachment",
        )


class PdfPreviewMixin:
    template_name = "reports/pdf_preview.html"
    export_name = ""
    page_title = ""
    back_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.copy()
        query.pop("inline", None)
        query_string = query.urlencode()
        export_url = reverse(self.export_name, args=["pdf"])
        back_url = reverse(self.back_name)
        inline_url = f"{export_url}?inline=1"
        download_url = export_url
        if query_string:
            inline_url = f"{export_url}?{query_string}&inline=1"
            download_url = f"{export_url}?{query_string}"
            back_url = f"{back_url}?{query_string}"
        context.update(
            {
                "page_title": self.page_title,
                "section_label": "Pre-visualizacao",
                "inline_url": inline_url,
                "download_url": download_url,
                "back_url": back_url,
            }
        )
        return context


class FinancialReportPdfPreviewView(PdfPreviewMixin, FinancialReportView):
    export_name = "reports:financial_export"
    page_title = "Pre-visualizar relatorio financeiro"
    back_name = "reports:financial"


class ClinicAdhesionReportView(PeriodReportMixin, RoleRequiredMixin, TemplateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    template_name = "reports/clinic_report.html"

    def get_filters(self):
        return {
            "professional": (self.request.GET.get("professional") or "").strip(),
            "plan": (self.request.GET.get("plan") or "").strip(),
            "patient_status": (self.request.GET.get("patient_status") or "").strip(),
            "patient": (self.request.GET.get("patient") or "").strip(),
        }

    def filter_patients(self, queryset, filters):
        if filters["professional"]:
            queryset = queryset.filter(
                professional_assignments__professional_id=filters["professional"],
                professional_assignments__active=True,
            )
        if filters["plan"]:
            queryset = queryset.filter(memberships__plan_id=filters["plan"])
        if filters["patient_status"] == "active":
            queryset = queryset.filter(active=True)
        elif filters["patient_status"] == "inactive":
            queryset = queryset.filter(active=False)
        if filters["patient"]:
            queryset = queryset.filter(full_name__icontains=filters["patient"])
        return queryset.distinct()

    def get_report_data(self):
        period = self.get_period()
        filters = self.get_filters()
        start = period["start"]
        end = period["end"]

        patient_scope = self.filter_patients(Patient.objects.all(), filters)
        patient_ids = patient_scope.values_list("id", flat=True)
        memberships = Membership.objects.select_related("patient", "plan").filter(patient_id__in=patient_ids)
        appointments = Appointment.objects.select_related("patient", "professional").filter(
            patient_id__in=patient_ids,
            starts_at__date__gte=start,
            starts_at__date__lte=end,
        )
        if filters["professional"]:
            appointments = appointments.filter(professional_id=filters["professional"])

        new_memberships = memberships.filter(created_at__date__gte=start, created_at__date__lte=end)
        active_memberships = memberships.filter(status=Membership.Status.ACTIVE)
        completed_appointments = appointments.filter(status=Appointment.Status.COMPLETED)
        canceled_appointments = appointments.filter(status=Appointment.Status.CANCELED)
        no_show_appointments = appointments.filter(status=Appointment.Status.NO_SHOW)
        total_scheduled = appointments.exclude(status=Appointment.Status.REQUESTED)

        active_patients_count = patient_scope.filter(active=True).count()
        inactive_patients_count = patient_scope.filter(active=False).count()
        active_patient_ratio = percent(active_patients_count, active_patients_count + inactive_patients_count)
        no_show_rate = percent(no_show_appointments.count(), total_scheduled.count())
        average_sessions_per_active_patient = (
            as_decimal(completed_appointments.count()) / as_decimal(active_patients_count)
            if active_patients_count
            else ZERO
        ).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)

        if no_show_rate <= Decimal("10.0") and completed_appointments.count() >= active_memberships.count():
            adhesion_label = "Adesao forte"
            adhesion_tone = "success"
            adhesion_summary = "A operacao mostra boa frequencia e baixa perda de atendimentos."
        elif no_show_rate <= Decimal("20.0"):
            adhesion_label = "Em acompanhamento"
            adhesion_tone = "warning"
            adhesion_summary = "A demanda esta sustentada, mas o engajamento merece acompanhamento."
        else:
            adhesion_label = "Risco de evasao"
            adhesion_tone = "danger"
            adhesion_summary = "O volume de faltas indica risco para a adesao da clinica."

        appointments_by_month = list(
            appointments.annotate(month=TruncMonth("starts_at"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )
        appointments_by_professional_rows = list(
            appointments.values("professional__full_name", "professional__specialty")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=Q(status=Appointment.Status.COMPLETED)),
                no_show=Count("id", filter=Q(status=Appointment.Status.NO_SHOW)),
            )
            .order_by("-completed", "professional__full_name")
        )
        appointments_by_professional = [
            {
                "label": row["professional__full_name"] or "Sem profissional",
                "specialty": dict(Professional.Specialty.choices).get(
                    row["professional__specialty"],
                    row["professional__specialty"] or "-",
                ),
                "total": row["total"],
                "completed": row["completed"],
                "no_show": row["no_show"],
                "percentage": percent_int(row["completed"], completed_appointments.count()),
            }
            for row in appointments_by_professional_rows
        ]

        top_patients_rows = list(
            appointments.values("patient__full_name")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=Q(status=Appointment.Status.COMPLETED)),
                no_show=Count("id", filter=Q(status=Appointment.Status.NO_SHOW)),
            )
            .order_by("-completed", "-total", "patient__full_name")[:10]
        )
        top_patients = [
            {
                "label": row["patient__full_name"],
                "total": row["total"],
                "completed": row["completed"],
                "no_show": row["no_show"],
                "percentage": percent_int(row["completed"], completed_appointments.count()),
            }
            for row in top_patients_rows
        ]

        plan_mix_rows = list(
            active_memberships.values("plan__name")
            .annotate(total=Count("id"))
            .order_by("-total", "plan__name")
        )
        plan_mix = [
            {
                "label": row["plan__name"] or "Sem plano",
                "total": row["total"],
                "percentage": percent_int(row["total"], active_memberships.count()),
            }
            for row in plan_mix_rows
        ]

        booking_source_rows = list(
            appointments.values("booking_source")
            .annotate(total=Count("id"))
            .order_by("-total", "booking_source")
        )
        booking_sources = [
            {
                "label": dict(Appointment.BookingSource.choices).get(row["booking_source"], row["booking_source"]),
                "total": row["total"],
                "percentage": percent_int(row["total"], appointments.count()),
            }
            for row in booking_source_rows
        ]

        patient_status_rows = [
            {
                "label": "Pacientes ativos",
                "total": active_patients_count,
                "percentage": percent_int(active_patients_count, active_patients_count + inactive_patients_count),
            },
            {
                "label": "Pacientes inativos",
                "total": inactive_patients_count,
                "percentage": percent_int(inactive_patients_count, active_patients_count + inactive_patients_count),
            },
        ]

        active_assignments = ProfessionalPatientAssignment.objects.filter(
            patient_id__in=patient_ids,
            active=True,
        ).count()

        return {
            "report_section": "clinic",
            "can_access_audit": user_can_access_audit(self.request.user),
            **self.get_period_context(),
            "selected_professional": filters["professional"],
            "selected_plan": filters["plan"],
            "selected_patient_status": filters["patient_status"],
            "selected_patient": filters["patient"],
            "professional_choices": Professional.objects.filter(active=True).order_by("full_name"),
            "plan_choices": ServicePlan.objects.filter(active=True).order_by("name"),
            "patient_status_choices": [
                ("", "Todos"),
                ("active", "Ativos"),
                ("inactive", "Inativos"),
            ],
            "new_memberships_count": new_memberships.count(),
            "active_memberships_count": active_memberships.count(),
            "completed_appointments_count": completed_appointments.count(),
            "canceled_appointments_count": canceled_appointments.count(),
            "no_show_appointments_count": no_show_appointments.count(),
            "active_patients_count": active_patients_count,
            "inactive_patients_count": inactive_patients_count,
            "active_assignments_count": active_assignments,
            "no_show_rate": no_show_rate,
            "active_patient_ratio": active_patient_ratio,
            "average_sessions_per_active_patient": average_sessions_per_active_patient,
            "adhesion_label": adhesion_label,
            "adhesion_tone": adhesion_tone,
            "adhesion_summary": adhesion_summary,
            "appointments_by_month": appointments_by_month,
            "appointments_by_professional": appointments_by_professional,
            "top_patients": top_patients,
            "plan_mix": plan_mix,
            "booking_sources": booking_sources,
            "patient_status_rows": patient_status_rows,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_report_data())
        return context


class ClinicAdhesionReportExportView(ClinicAdhesionReportView, View):
    def get(self, request, *args, **kwargs):
        data = self.get_report_data()
        if kwargs["export_format"] == "xlsx":
            return self.export_xlsx(data)
        return self.export_pdf(data)

    def summary_rows(self, data):
        return [
            ("Periodo", f"{data['start']} a {data['end']}"),
            ("Novas adesoes", data["new_memberships_count"]),
            ("Mensalidades ativas", data["active_memberships_count"]),
            ("Atendimentos realizados", data["completed_appointments_count"]),
            ("Pacientes ativos", data["active_patients_count"]),
            ("Pacientes inativos", data["inactive_patients_count"]),
            ("Faltas", data["no_show_appointments_count"]),
            ("Taxa de faltas", f"{data['no_show_rate']}%"),
            ("Media de atendimentos por paciente ativo", data["average_sessions_per_active_patient"]),
            ("Leitura operacional", data["adhesion_label"]),
        ]

    def export_xlsx(self, data):
        sheets = [
            ("Resumo adesao", ["Indicador", "Valor"], self.summary_rows(data)),
            (
                "Atendimentos por mes",
                ["Mes", "Atendimentos"],
                [(row["month"].strftime("%m/%Y"), row["total"]) for row in data["appointments_by_month"]],
            ),
            (
                "Profissionais",
                ["Profissional", "Especialidade", "Total", "Realizados", "Faltas"],
                [
                    (row["label"], row["specialty"], row["total"], row["completed"], row["no_show"])
                    for row in data["appointments_by_professional"]
                ],
            ),
            (
                "Pacientes",
                ["Paciente", "Total", "Realizados", "Faltas"],
                [
                    (row["label"], row["total"], row["completed"], row["no_show"])
                    for row in data["top_patients"]
                ],
            ),
            (
                "Planos ativos",
                ["Plano", "Quantidade", "Percentual"],
                [(row["label"], row["total"], f"{row['percentage']}%") for row in data["plan_mix"]],
            ),
            (
                "Origem agendamentos",
                ["Origem", "Quantidade", "Percentual"],
                [(row["label"], row["total"], f"{row['percentage']}%") for row in data["booking_sources"]],
            ),
        ]
        return xlsx_response("relatorio_adesao_clinica_lume.xlsx", sheets)

    def export_pdf(self, data):
        sections = [
            ("Resumo de adesao", [f"{label}: {value}" for label, value in self.summary_rows(data)]),
            ("Leitura operacional", [data["adhesion_summary"]]),
        ]
        sections[0] = (
            "Resumo de adesao",
            [
                f"{label}: {br_date(data['start'])} a {br_date(data['end'])}" if label == "Periodo" else f"{label}: {value}"
                for label, value in self.summary_rows(data)
            ],
        )
        charts = [
            {
                "title": "Atendimentos por profissional",
                "rows": [
                    {
                        "label": row["label"],
                        "value": row["completed"],
                        "display": f"{row['completed']} realizados",
                    }
                    for row in data["appointments_by_professional"]
                ],
            },
            {
                "title": "Distribuicao de planos ativos",
                "rows": [
                    {
                        "label": row["label"],
                        "value": row["total"],
                        "display": f"{row['total']} - {br_percent(row['percentage'])}",
                    }
                    for row in data["plan_mix"]
                ],
            },
        ]
        tables = [
            (
                "Atendimentos por profissional",
                ["Profissional", "Especialidade", "Total", "Realizados", "Faltas"],
                [
                    (row["label"], row["specialty"], row["total"], row["completed"], row["no_show"])
                    for row in data["appointments_by_professional"]
                ],
            ),
            (
                "Pacientes com mais atendimentos",
                ["Paciente", "Total", "Realizados", "Faltas"],
                [(row["label"], row["total"], row["completed"], row["no_show"]) for row in data["top_patients"]],
            ),
            (
                "Planos ativos",
                ["Plano", "Quantidade", "Percentual"],
                [(row["label"], row["total"], br_percent(row["percentage"])) for row in data["plan_mix"]],
            ),
        ]
        return pdf_response(
            "relatorio_adesao_clinica_lume.pdf",
            "Relatorio de gestao de adesao - Lume",
            sections=sections,
            charts=charts,
            tables=tables,
            landscape_page=True,
            disposition="inline" if self.request.GET.get("inline") == "1" else "attachment",
        )


class ClinicAdhesionReportPdfPreviewView(PdfPreviewMixin, ClinicAdhesionReportView):
    export_name = "reports:clinic_export"
    page_title = "Pre-visualizar relatorio de adesao"
    back_name = "reports:clinic"


class AuditReportView(ManagementAccessMixin, ListView):
    model = AuditLog
    template_name = "reports/audit_report.html"
    context_object_name = "logs"
    paginate_by = 20

    def get_filters(self):
        return {
            "q": (self.request.GET.get("q") or "").strip(),
            "action": (self.request.GET.get("action") or "").strip(),
            "model": (self.request.GET.get("model") or "").strip(),
            "actor": (self.request.GET.get("actor") or "").strip(),
            "date_from": (self.request.GET.get("date_from") or "").strip(),
            "date_to": (self.request.GET.get("date_to") or "").strip(),
        }

    def get_filtered_queryset(self):
        filters = self.get_filters()
        queryset = AuditLog.objects.select_related("actor").all()
        if filters["q"]:
            queryset = queryset.filter(
                Q(actor__username__icontains=filters["q"])
                | Q(model_name__icontains=filters["q"])
                | Q(object_repr__icontains=filters["q"])
                | Q(action__icontains=filters["q"])
            )
        if filters["action"]:
            queryset = queryset.filter(action=filters["action"])
        if filters["model"]:
            queryset = queryset.filter(model_name=filters["model"])
        if filters["actor"]:
            queryset = queryset.filter(actor__id=filters["actor"])
        if filters["date_from"]:
            queryset = queryset.filter(created_at__date__gte=filters["date_from"])
        if filters["date_to"]:
            queryset = queryset.filter(created_at__date__lte=filters["date_to"])
        return queryset

    def get_queryset(self):
        return self.get_filtered_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered = self.get_filtered_queryset()
        filters = self.get_filters()
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context.update(
            {
                "report_section": "audit",
                "can_access_audit": True,
                "action_choices": AuditLog.Action.choices,
                "model_choices": AuditLog.objects.order_by("model_name").values_list("model_name", flat=True).distinct(),
                "actor_choices": UserProfile.objects.exclude(user__isnull=True)
                .select_related("user")
                .order_by("user__username"),
                "selected_action": filters["action"],
                "selected_model": filters["model"],
                "selected_actor": filters["actor"],
                "date_from": filters["date_from"],
                "date_to": filters["date_to"],
                "q": filters["q"],
                "querystring": query_params.urlencode(),
                "audit_total": filtered.count(),
                "audit_created_total": filtered.filter(action=AuditLog.Action.CREATED).count(),
                "audit_updated_total": filtered.filter(action=AuditLog.Action.UPDATED).count(),
                "audit_deleted_total": filtered.filter(action=AuditLog.Action.DELETED).count(),
                "audit_user_total": filtered.exclude(actor__isnull=True).values("actor").distinct().count(),
                "audit_model_total": filtered.values("model_name").distinct().count(),
            }
        )
        for log in context["logs"]:
            log.actor_display = log.actor.username if log.actor else "sistema"
            log.display_changes = [
                {
                    "field": field,
                    "old": prettify_value(change.get("old")),
                    "new": prettify_value(change.get("new")),
                }
                for field, change in (log.changes or {}).items()
            ]
        return context


class AuditReportExportView(ManagementAccessMixin, View):
    def get(self, request, *args, **kwargs):
        view = AuditReportView()
        view.request = request
        queryset = view.get_filtered_queryset().select_related("actor")
        if kwargs["export_format"] == "xlsx":
            return self.export_xlsx(queryset)
        return self.export_pdf(queryset)

    def export_xlsx(self, queryset):
        rows = [
            (
                log.created_at.strftime("%d/%m/%Y %H:%M"),
                log.actor.username if log.actor else "sistema",
                log.get_action_display(),
                log.model_name,
                log.object_repr,
                "; ".join(
                    f"{field}: {prettify_value(change.get('old'))} -> {prettify_value(change.get('new'))}"
                    for field, change in (log.changes or {}).items()
                )
                or "Sem detalhes",
            )
            for log in queryset
        ]
        return xlsx_response(
            "relatorio_auditoria_lume.xlsx",
            [("Auditoria", ["Data", "Usuario", "Acao", "Modelo", "Objeto", "Alteracoes"], rows)],
        )

    def export_pdf(self, queryset):
        tables = [
            (
                "Eventos de auditoria",
                ["Data", "Usuario", "Acao", "Modelo", "Objeto", "Alteracoes"],
                [
                    (
                        log.created_at.strftime("%d/%m/%Y %H:%M"),
                        log.actor.username if log.actor else "sistema",
                        log.get_action_display(),
                        log.model_name,
                        log.object_repr,
                        "; ".join(
                            f"{field}: {prettify_value(change.get('old'))} -> {prettify_value(change.get('new'))}"
                            for field, change in (log.changes or {}).items()
                        )
                        or "Sem detalhes",
                    )
                    for log in queryset
                ],
            )
        ]
        return pdf_response(
            "relatorio_auditoria_lume.pdf",
            "Relatorio de auditoria - Lume",
            sections=[("Resumo", [f"Eventos exportados: {queryset.count()}"])],
            tables=tables,
            landscape_page=True,
            disposition="inline" if self.request.GET.get("inline") == "1" else "attachment",
        )


class AuditReportPdfPreviewView(PdfPreviewMixin, AuditReportView):
    export_name = "reports:audit_export"
    page_title = "Pre-visualizar relatorio de auditoria"
    back_name = "reports:audit"
