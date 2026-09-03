from django.urls import path

from cycles import views

urlpatterns = [
    path("projects/<int:project_pk>/cycles/new/", views.cycle_create, name="cycle-create"),
    path("cycles/<int:pk>/close/", views.cycle_close, name="cycle-close"),
    # Card board (issue #8): the board is scoped to a cycle, edit/delete
    # are scoped to a card id directly (no cycle in the path -- see
    # `cycles.views.card_edit`/`card_delete`'s docstrings on why lookups
    # are scoped to `author=request.user` instead).
    path("cycles/<int:cycle_pk>/board/", views.card_board, name="card-board"),
    path("cycles/<int:cycle_pk>/cards/", views.card_create, name="card-create"),
    path("cards/<int:pk>/", views.card_edit, name="card-edit"),
    path("cards/<int:pk>/delete/", views.card_delete, name="card-delete"),
]
