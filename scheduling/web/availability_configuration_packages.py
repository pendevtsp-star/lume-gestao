"""Availability, agenda configuration, and service package views."""

from scheduling.web.common import *  # noqa: F401,F403

class ProfessionalAvailabilityAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class ProfessionalAvailabilityListView(ProfessionalAvailabilityAccessMixin, SearchableListView, ListView):
    model = ProfessionalAvailability
    template_name = "scheduling/availability_list.html"
    context_object_name = "availabilities"
    paginate_by = 12
    search_fields = ["professional__full_name", "notes"]

    def get_queryset(self):
        return filter_availability_search(availabilities_for_user(self.request.user), self.request.GET.get("q", "").strip())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        availabilities = list(self.get_queryset())
        grouped = {}
        for availability in availabilities:
            professional = availability.professional
            grouped.setdefault(
                professional.pk,
                {
                    "professional": professional,
                    "days": {weekday: [] for weekday, _label in ProfessionalAvailability.Weekday.choices},
                    "total": 0,
                    "active": 0,
                },
            )
            grouped[professional.pk]["days"][availability.weekday].append(availability)
            grouped[professional.pk]["total"] += 1
            if availability.active:
                grouped[professional.pk]["active"] += 1

        context["weekday_choices"] = ProfessionalAvailability.Weekday.choices
        availability_boards = []
        for board in grouped.values():
            board["weekdays"] = [
                {"value": weekday, "label": label, "items": board["days"][weekday]}
                for weekday, label in ProfessionalAvailability.Weekday.choices
            ]
            availability_boards.append(board)
        context["availability_boards"] = sorted(
            availability_boards,
            key=lambda item: item["professional"].full_name,
        )
        return context

class ProfessionalAvailabilityCreateView(ProfessionalAvailabilityAccessMixin, FormView):
    form_class = ProfessionalAvailabilityBatchForm
    template_name = "scheduling/availability_form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        created_count = 0
        updated_count = 0
        with transaction.atomic():
            for weekday in form.cleaned_data["weekdays"]:
                for starts_at, ends_at in form.cleaned_data["time_windows"]:
                    _availability, created = ProfessionalAvailability.objects.update_or_create(
                        professional=form.cleaned_data["professional"],
                        weekday=weekday,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        valid_from=form.cleaned_data["valid_from"],
                        defaults={
                            "valid_until": form.cleaned_data["valid_until"],
                            "session_capacity": form.cleaned_data["session_capacity"],
                            "active": form.cleaned_data["active"],
                            "notes": form.cleaned_data.get("notes", ""),
                        },
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
        message = f"{created_count} disponibilidade(s) criada(s)"
        if updated_count:
            message += f" e {updated_count} atualizada(s)"
        messages.success(self.request, f"{message} com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": self.page_title,
                "section_label": self.section_label,
                "back_url": reverse(self.back_url_name),
            }
        )
        return context


class ProfessionalAvailabilityUpdateView(FormContextMixin, ProfessionalAvailabilityAccessMixin, UpdateView):
    model = ProfessionalAvailability
    form_class = ProfessionalAvailabilityForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_queryset(self):
        return availabilities_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Disponibilidade atualizada com sucesso.")
        return super().form_valid(form)


class ProfessionalAvailabilityDeleteView(DeletionDecisionMixin, FormContextMixin, ProfessionalAvailabilityAccessMixin, DeleteView):
    model = ProfessionalAvailability
    default_delete_action = DELETE_ACTION_NOW
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Excluir disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"
    entity_label = "disponibilidade"

    def get_queryset(self):
        return availabilities_for_user(self.request.user)

    def perform_delete_now(self):
        hard_delete_availability(self.object)

    def perform_deactivate(self):
        mark_active_object_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        availability = self.object
        context.update(
            {
                "object_name": (
                    f"{availability.professional.full_name} - {availability.get_weekday_display()} "
                    f"{availability.starts_at:%H:%M} ate {availability.ends_at:%H:%M}"
                ),
                "entity_label": "disponibilidade",
                "delete_explanation": (
                    "Escolha se deseja apenas retirar esta regra da agenda ativa ou remover definitivamente."
                ),
            }
        )
        return context


class AgendaSettingsUpdateView(FormContextMixin, AgendaSettingsAccessMixin, UpdateView):
    model = ClinicSettings
    form_class = AgendaSettingsForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Configuracoes da agenda"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"

    def get_object(self, queryset=None):
        return ClinicSettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Configuracoes da agenda atualizadas com sucesso.")
        return super().form_valid(form)


class ServicePackageListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePackage
    template_name = "scheduling/package_list.html"
    context_object_name = "packages"
    paginate_by = 12
    search_fields = ["membership__patient__full_name", "membership__plan__name", "status"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("membership__patient", "membership__plan")
            .exclude(status=ServicePackage.Status.CANCELED)
        )


class ServicePackageAdjustmentListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePackageAdjustment
    template_name = "scheduling/package_adjustment_list.html"
    context_object_name = "adjustments"
    paginate_by = 20
    search_fields = [
        "service_package__membership__patient__full_name",
        "service_package__membership__plan__name",
        "reason",
        "notes",
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "service_package__membership__patient",
                "service_package__membership__plan",
                "appointment",
                "created_by",
            )
        )


class ServicePackageCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Adesao"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def get_initial(self):
        initial = super().get_initial()
        patient_id = self.request.GET.get("patient")
        plan_id = self.request.GET.get("plan")
        if patient_id:
            initial["patient"] = patient_id
        if plan_id:
            initial["plan"] = plan_id
        return initial

    def form_valid(self, form):
        patient = form.cleaned_data["patient"]
        plan = form.cleaned_data["plan"]
        messages.success(self.request, f"Adesao criada para {patient.full_name} em {plan.name}.")
        return super().form_valid(form)


class ServicePackageUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Adesao"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def form_valid(self, form):
        patient = form.cleaned_data["patient"]
        plan = form.cleaned_data["plan"]
        messages.success(self.request, f"Adesao atualizada para {patient.full_name} em {plan.name}.")
        return super().form_valid(form)


class ServicePackageDeleteView(DeletionDecisionMixin, FormContextMixin, FinanceAccessMixin, DeleteView):
    model = ServicePackage
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Excluir adesao"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"
    entity_label = "adesao"

    def perform_delete_now(self):
        hard_delete_service_package(self.object)

    def perform_deactivate(self):
        mark_package_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        package = self.object
        context.update(
            {
                "object_name": f"{package.membership.patient.full_name} - {package.membership.plan.name}",
                "entity_label": "adesao",
                "delete_explanation": (
                    "Escolha se deseja inativar esta adesao ou remover definitivamente seus registros."
                ),
            }
        )
        return context
