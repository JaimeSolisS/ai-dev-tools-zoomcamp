from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):
    """Thin wrapper over UserCreationForm: adds a required "display name"
    field that is stored in User.first_name (see the AUTH_USER_MODEL
    decision in issue #4 -- no custom user model, no profile table).

    Username/password handling (including duplicate-username and
    AUTH_PASSWORD_VALIDATORS errors) is inherited unchanged from
    UserCreationForm.
    """

    first_name = forms.CharField(
        label="Display name",
        max_length=150,
        required=True,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        if commit:
            user.save()
        return user
