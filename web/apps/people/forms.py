"""Form for adding and editing a person (admin only)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.people.models import Person


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ("employee_code", "full_name", "department", "is_active", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def clean_employee_code(self):
        code = self.cleaned_data["employee_code"].strip()
        clash = Person.objects.filter(employee_code__iexact=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("This employee code is already used."))
        return code
