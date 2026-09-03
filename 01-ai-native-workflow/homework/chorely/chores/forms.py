from django import forms
from django.utils import timezone

from .models import Category, Chore, User


class ChoreForm(forms.ModelForm):
    assignees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Chore
        fields = ["title", "description", "due_date", "category", "assignees"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, editing=False, **kwargs):
        self.user = user
        self.editing = editing
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()

        if user is not None and not user.is_admin:
            # Members may only create/hold chores assigned to themselves.
            self.fields["assignees"].queryset = User.objects.filter(pk=user.pk)
            self.fields["assignees"].initial = [user.pk]
            self.fields["assignees"].disabled = True
        elif user is not None:
            self.fields["assignees"].queryset = User.objects.filter(
                household=user.household, is_active=True
            )

    def clean_due_date(self):
        due_date = self.cleaned_data["due_date"]
        if not self.editing and due_date < timezone.localdate():
            raise forms.ValidationError("Due date must be today or in the future.")
        return due_date

    def clean_assignees(self):
        assignees = self.cleaned_data.get("assignees")
        if self.user is not None and not self.user.is_admin:
            return User.objects.filter(pk=self.user.pk)
        return assignees


class MemberCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    display_name = forms.CharField(max_length=100)
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username
