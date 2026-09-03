from django import forms
from django.contrib.auth.models import User

from cycles.models import Card, FeedbackCycle


class FeedbackCycleForm(forms.ModelForm):
    """`project` is assigned by the view, never client-settable (mirrors
    `ProjectForm`'s treatment of `owner`). `opens_at`/`closes_at`/`status`
    are never editable fields here -- they're stamped by the model/view.

    The facilitator queryset is every member of the target project, not
    only `FACILITATOR`-role members (issue #7: `Membership.role` is a
    default suggestion, not a constraint). Restricting the queryset to
    project members is what makes selecting a non-member a form error --
    `ModelChoiceField` rejects a pk outside its queryset as an invalid
    choice.
    """

    class Meta:
        model = FeedbackCycle
        fields = ["week_start", "facilitator"]
        widgets = {
            "week_start": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, project, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields["facilitator"].queryset = User.objects.filter(
            memberships__project=project
        ).distinct()


class CardForm(forms.ModelForm):
    """`cycle`, `category`, `author`, and `position` are all assigned by
    the view, never client-settable -- `category` comes from which
    column's form was submitted (see `cycles/views.py`), not a field on
    this form. `text` is the only thing the client actually controls.

    Issue #8: empty or whitespace-only text is rejected as a form error,
    never a silent no-op and never a blank `Card` row.
    """

    class Meta:
        model = Card
        fields = ["text", "is_anonymous"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
        }

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("This field can't be empty.")
        return text
