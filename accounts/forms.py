from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q

from accounts.models import UserProfile
from core.forms import StyledModelForm
from patients.models import Patient
from team.models import Professional


class UserAccountForm(forms.ModelForm):
    password = forms.CharField(label="senha temporaria", widget=forms.PasswordInput, required=False)
    role = forms.ChoiceField(label="perfil", choices=UserProfile.Role.choices)
    patient = forms.ModelChoiceField(label="paciente vinculado", queryset=Patient.objects.none(), required=False)
    professional = forms.ModelChoiceField(label="profissional vinculado", queryset=Professional.objects.none(), required=False)

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "checkbox")
            else:
                field.widget.attrs.setdefault("class", "field-control")

        self.fields["patient"].queryset = Patient.objects.filter(active=True)
        self.fields["professional"].queryset = Professional.objects.filter(active=True)

        if self.instance.pk and hasattr(self.instance, "profile"):
            profile = self.instance.profile
            self.fields["role"].initial = profile.role
            self.fields["patient"].initial = profile.patient
            self.fields["professional"].initial = profile.professional

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        patient = cleaned.get("patient")
        professional = cleaned.get("professional")

        if role == UserProfile.Role.PATIENT and not patient:
            self.add_error("patient", "Vincule um paciente para este perfil.")
        if role == UserProfile.Role.PROFESSIONAL and not professional:
            self.add_error("professional", "Vincule um profissional para este perfil.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_unusable_password()

        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data["role"]
            profile.patient = self.cleaned_data.get("patient")
            profile.professional = self.cleaned_data.get("professional")
            profile.save()
        return user


class UserProfileForm(StyledModelForm):
    class Meta:
        model = UserProfile
        fields = [
            "role",
            "patient",
            "professional",
            "phone",
            "whatsapp_number",
            "whatsapp_notifications_enabled",
            "photo",
        ]


class UserSelfSettingsForm(forms.Form):
    username = forms.CharField(label="login", max_length=150)
    first_name = forms.CharField(label="nome", max_length=150, required=False)
    last_name = forms.CharField(label="sobrenome", max_length=150, required=False)
    email = forms.EmailField(label="e-mail", required=False)
    phone = forms.CharField(label="telefone", max_length=30, required=False)
    whatsapp_number = forms.CharField(label="WhatsApp para avisos", max_length=30, required=False)
    whatsapp_notifications_enabled = forms.BooleanField(label="habilitar avisos futuros por WhatsApp", required=False)
    photo = forms.ImageField(label="foto pessoal", required=False)
    remove_photo = forms.BooleanField(label="remover foto atual", required=False, widget=forms.HiddenInput)
    current_password = forms.CharField(
        label="senha atual",
        widget=forms.PasswordInput,
        required=False,
        help_text="Obrigatoria apenas para trocar a senha.",
    )
    new_password1 = forms.CharField(label="nova senha", widget=forms.PasswordInput, required=False)
    new_password2 = forms.CharField(label="confirmar nova senha", widget=forms.PasswordInput, required=False)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile = profile
        photo_owner = profile.patient or profile.professional or profile
        self.photo_owner = photo_owner
        self.show_whatsapp_settings = profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
        } or self.user.is_superuser
        self.fields["username"].initial = self.user.username
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email
        self.fields["phone"].initial = profile.phone
        self.fields["whatsapp_number"].initial = profile.whatsapp_number
        self.fields["whatsapp_notifications_enabled"].initial = profile.whatsapp_notifications_enabled

        if not self.show_whatsapp_settings:
            self.fields.pop("whatsapp_number")
            self.fields.pop("whatsapp_notifications_enabled")

        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            else:
                widget.attrs.setdefault("class", "field-control")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        user_model = get_user_model()
        exists = user_model.objects.exclude(pk=self.user.pk).filter(username__iexact=username).exists()
        if exists:
            raise forms.ValidationError("Este login ja esta em uso.")
        return username

    def clean(self):
        cleaned = super().clean()
        current_password = cleaned.get("current_password")
        new_password1 = cleaned.get("new_password1")
        new_password2 = cleaned.get("new_password2")

        if new_password1 or new_password2:
            if not current_password:
                self.add_error("current_password", "Informe a senha atual para trocar a senha.")
            elif not self.user.check_password(current_password):
                self.add_error("current_password", "Senha atual incorreta.")
            if new_password1 != new_password2:
                self.add_error("new_password2", "As senhas nao conferem.")
            if new_password1:
                try:
                    validate_password(new_password1, self.user)
                except forms.ValidationError as error:
                    self.add_error("new_password1", error)
        return cleaned

    def save(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.user.username = self.cleaned_data["username"]
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.email = self.cleaned_data["email"]
        if self.cleaned_data.get("new_password1"):
            self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save()

        profile.phone = self.cleaned_data["phone"]
        if "whatsapp_number" in self.cleaned_data:
            profile.whatsapp_number = self.cleaned_data["whatsapp_number"]
            profile.whatsapp_notifications_enabled = self.cleaned_data.get("whatsapp_notifications_enabled", False)
        profile.save()

        photo = self.cleaned_data.get("photo")
        if self.cleaned_data.get("remove_photo") and getattr(self.photo_owner, "photo", None):
            self.photo_owner.photo.delete(save=False)
            self.photo_owner.photo = ""
            self.photo_owner.save(update_fields=["photo", "updated_at"] if hasattr(self.photo_owner, "updated_at") else ["photo"])
        elif photo:
            self.photo_owner.photo = photo
            self.photo_owner.save(update_fields=["photo", "updated_at"] if hasattr(self.photo_owner, "updated_at") else ["photo"])
        return self.user


class PasswordRecoveryRequestForm(forms.Form):
    identifier = forms.CharField(label="e-mail ou login", max_length=254)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.users = []
        self.fields["identifier"].widget.attrs.setdefault("class", "field-control")
        self.fields["identifier"].widget.attrs.setdefault("autocomplete", "username")

    def clean_identifier(self):
        identifier = self.cleaned_data["identifier"].strip()
        user_model = get_user_model()
        if "@" in identifier:
            users = user_model.objects.filter(email__iexact=identifier, is_active=True)
        else:
            users = user_model.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier), is_active=True)

        self.users = [user for user in users if user.has_usable_password()]
        if not self.users:
            raise forms.ValidationError("Usuario inexistente.")
        if not any(user.email for user in self.users):
            raise forms.ValidationError("Este usuario nao possui e-mail cadastrado para recuperacao.")
        return identifier
