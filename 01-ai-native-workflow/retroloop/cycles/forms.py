from django import forms
from django.contrib.auth.models import User

from cycles.models import FeedbackCycle


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
