from django import forms

from core.forms import StyledModelForm
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment


RECORD_TYPE_CONFIGS = {
    ProfessionalNote.RecordType.CLINICAL_EVALUATION: {
        "title": "Avaliacao clinica",
        "sections": [
            {
                "title": "Historia clinica",
                "description": "Dados de anamnese e historico do paciente.",
                "fields": [
                    ("clinical_history", "Historia clinica / Anamnese", "textarea", "Dados relativos a doenca"),
                    (
                        "current_disease_history",
                        "Historia da doenca atual",
                        "textarea",
                        "Duracao, intensidade, evolucao e fatores de alivio.",
                    ),
                    (
                        "past_disease_history",
                        "Historia da doenca pregressa",
                        "textarea",
                        "Informacoes clinicas anteriores do paciente.",
                    ),
                ],
            },
            {
                "title": "Habitos e antecedentes",
                "description": "Marque habitos relevantes e complemente quando necessario.",
                "fields": [
                    (
                        "life_habits",
                        "Habitos de vida",
                        "multiple",
                        [
                            ("tabagismo", "Tabagismo"),
                            ("alcool", "Consumo de bebida alcoolica"),
                            ("sedentarismo", "Sedentarismo"),
                            ("outros", "Outro(s)"),
                        ],
                    ),
                    (
                        "personal_history",
                        "Antecedentes pessoais",
                        "textarea",
                        "Historico do estado de saude passado do paciente.",
                    ),
                    (
                        "family_history",
                        "Antecedentes familiares",
                        "textarea",
                        "Historico familiar relevante.",
                    ),
                    (
                        "previous_treatments",
                        "Tratamentos realizados",
                        "textarea",
                        "Historico dos tratamentos ja realizados.",
                    ),
                ],
            },
        ],
    },
    ProfessionalNote.RecordType.DIAGNOSIS: {
        "title": "Diagnostico",
        "sections": [
            {
                "title": "Diagnostico",
                "description": "Registre a hipotese clinica e fisioterapeutica.",
                "fields": [
                    ("clinical_diagnosis", "Clinico", "textarea", ""),
                    ("physiotherapeutic_diagnosis", "Fisioterapeutico", "textarea", ""),
                    ("main_complaint", "Queixa principal", "textarea", ""),
                ],
            },
        ],
    },
    ProfessionalNote.RecordType.PHYSICAL_EXAM: {
        "title": "Exame fisico clinico",
        "sections": [
            {
                "title": "Sinais vitais",
                "description": "Parametros objetivos coletados no atendimento.",
                "fields": [
                    ("blood_pressure", "Pressao arterial", "text", "Ex.: 120x80 mmHg"),
                    ("heart_rate", "Frequencia cardiaca", "text", "bpm"),
                    ("temperature", "Temperatura", "text", "C"),
                ],
            },
            {
                "title": "Apresentacao do paciente",
                "description": "Marque as condicoes observadas no exame.",
                "fields": [
                    (
                        "patient_presentation",
                        "Apresentacao",
                        "multiple",
                        [
                            ("deambulando", "Deambulando"),
                            ("apoio_auxilio", "Deambulando com apoio / auxilio"),
                            ("cadeira_rodas", "Cadeira de rodas"),
                            ("claudicando", "Claudicando"),
                            ("internado", "Internado"),
                            ("orientado", "Orientado"),
                            ("restrito_leito", "Restrito ao leito"),
                        ],
                    ),
                    ("gait_type", "Tipo de marcha", "text", ""),
                ],
            },
            {
                "title": "Historico complementar",
                "description": "Itens rapidos para completar o exame.",
                "fields": [
                    ("complementary_exams", "Exames complementares", "textarea", "Informe exames ou escreva nao."),
                    ("medications", "Usa medicamentos?", "textarea", "Informe medicamentos ou escreva nao."),
                    ("surgeries", "Realizou cirurgia?", "textarea", "Informe cirurgias ou escreva nao."),
                    (
                        "inspection_palpation",
                        "Inspecao / Palpacao",
                        "multiple",
                        [
                            ("normal", "Normal"),
                            ("edema", "Edema"),
                            ("cicatrizacao_incompleta", "Cicatrizacao incompleta"),
                            ("eritemas", "Eritemas"),
                            ("outros", "Outros"),
                        ],
                    ),
                    ("semiology", "Semiologia", "textarea", "Testes e sintomas observados."),
                ],
            },
        ],
    },
    ProfessionalNote.RecordType.DAILY_EVOLUTION: {
        "title": "Evolucao diaria",
        "sections": [
            {
                "title": "Dados da sessao",
                "description": "Objetivo e foco do atendimento.",
                "fields": [],
            },
            {
                "title": "Selecoes do atendimento",
                "description": "Marque os equipamentos, grupos ou recursos utilizados.",
                "fields": [],
            },
            {
                "title": "Evolucao e conduta",
                "description": "Resumo objetivo para acompanhar a resposta do paciente.",
                "fields": [],
            },
        ],
    },
}


def note_type_options():
    return [
        (ProfessionalNote.RecordType.CLINICAL_EVALUATION, "Avaliacao clinica"),
        (ProfessionalNote.RecordType.DIAGNOSIS, "Diagnostico"),
        (ProfessionalNote.RecordType.PHYSICAL_EXAM, "Exame fisico clinico"),
        (ProfessionalNote.RecordType.DAILY_EVOLUTION, "Evolucao diaria"),
    ]


class PatientForm(StyledModelForm):
    class Meta:
        model = Patient
        fields = [
            "full_name",
            "photo",
            "cpf",
            "birth_date",
            "phone",
            "email",
            "emergency_contact",
            "address",
            "clinical_notes",
            "active",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "clinical_notes": forms.Textarea(attrs={"rows": 4}),
        }


class ProfessionalPatientAssignmentForm(StyledModelForm):
    class Meta:
        model = ProfessionalPatientAssignment
        fields = ["patient", "professional", "active", "notes"]


class ProfessionalNoteForm(StyledModelForm):
    exercise_groups = forms.MultipleChoiceField(
        label="Selecoes do atendimento",
        choices=ProfessionalNote.EXERCISE_GROUP_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ProfessionalNote
        fields = [
            "patient",
            "professional",
            "title",
            "record_type",
            "session_focus",
            "objective",
            "exercise_groups",
            "pain_level",
            "clinical_status",
            "conduct",
            "body",
        ]
        widgets = {
            "record_type": forms.HiddenInput(),
            "objective": forms.TextInput(attrs={"placeholder": "Descreva o objetivo do atendimento"}),
            "body": forms.Textarea(attrs={"rows": 6, "placeholder": "Observacoes livres do profissional"}),
        }

    def __init__(self, *args, **kwargs):
        requested_record_type = kwargs.pop("record_type", None)
        super().__init__(*args, **kwargs)
        self.dynamic_field_names = []
        self.record_type_value = self._resolve_record_type(requested_record_type)
        self.fields["title"].label = "Resumo"
        self.fields["record_type"].initial = self.record_type_value
        self.fields["pain_level"].widget = forms.Select(
            choices=[("", "Selecione")] + [(value, str(value)) for value in range(0, 11)]
        )
        self.fields["pain_level"].widget.attrs.setdefault("class", "field-control")
        if self.instance and self.instance.pk:
            self.fields["exercise_groups"].initial = self.instance.exercise_groups or []
        self._add_dynamic_fields()

    @property
    def record_config(self):
        return RECORD_TYPE_CONFIGS[self.record_type_value]

    @property
    def record_sections(self):
        return self.record_config["sections"]

    @property
    def is_daily_evolution(self):
        return self.record_type_value == ProfessionalNote.RecordType.DAILY_EVOLUTION

    @property
    def dynamic_sections(self):
        sections = []
        for section in self.record_sections:
            fields = [self[name] for name, *_ in section["fields"]]
            if fields:
                sections.append(
                    {
                        "title": section["title"],
                        "description": section["description"],
                        "fields": fields,
                    }
                )
        return sections

    def _resolve_record_type(self, requested_record_type):
        valid_types = set(RECORD_TYPE_CONFIGS)
        if requested_record_type in valid_types:
            return requested_record_type
        if self.instance and self.instance.pk and self.instance.record_type in valid_types:
            return self.instance.record_type
        if self.instance and self.instance.pk and self.instance.record_type == ProfessionalNote.RecordType.EVOLUTION:
            return ProfessionalNote.RecordType.DAILY_EVOLUTION
        return ProfessionalNote.RecordType.DAILY_EVOLUTION

    def _add_dynamic_fields(self):
        structured_data = self.instance.structured_data if self.instance and self.instance.pk else {}
        for section in self.record_sections:
            for name, label, field_type, config in section["fields"]:
                self.dynamic_field_names.append(name)
                initial = structured_data.get(name, [] if field_type == "multiple" else "")
                if field_type == "multiple":
                    self.fields[name] = forms.MultipleChoiceField(
                        label=label,
                        choices=config,
                        required=False,
                        initial=initial,
                        widget=forms.CheckboxSelectMultiple,
                    )
                elif field_type == "textarea":
                    self.fields[name] = forms.CharField(
                        label=label,
                        required=False,
                        initial=initial,
                        widget=forms.Textarea(attrs={"rows": 3, "placeholder": config}),
                    )
                else:
                    self.fields[name] = forms.CharField(
                        label=label,
                        required=False,
                        initial=initial,
                        widget=forms.TextInput(attrs={"placeholder": config}),
                    )
                widget = self.fields[name].widget
                if not isinstance(widget, forms.CheckboxSelectMultiple):
                    widget.attrs.setdefault("class", "field-control")

    def save(self, commit=True):
        self.instance.record_type = self.record_type_value
        self.instance.structured_data = {
            name: self.cleaned_data.get(name, [] if isinstance(self.fields[name], forms.MultipleChoiceField) else "")
            for name in self.dynamic_field_names
        }
        return super().save(commit=commit)
