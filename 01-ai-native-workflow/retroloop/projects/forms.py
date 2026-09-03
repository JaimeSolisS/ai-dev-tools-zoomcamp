from django import forms

from projects.models import Project


class ProjectForm(forms.ModelForm):
    """Only `name` is ever client-settable. `owner` and `join_token` are
    assigned by the view/model default, never the form (see issue #5)."""

    class Meta:
        model = Project
        fields = ["name"]
