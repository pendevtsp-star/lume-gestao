from django.urls import path

from lume_connect.views import (
    AddCommentView,
    CommentDeleteView,
    DownloadPostImageView,
    CommentEditView,
    FeedView,
    GenerateCaptionView,
    LogShareView,
    MarkNotificationsReadView,
    PostCreateView,
    PostDeleteView,
    PostEditView,
    ProfilePostsView,
    SharePostView,
    ToggleLikeView,
)

app_name = "lume_connect"

urlpatterns = [
    path("", FeedView.as_view(), name="feed"),
    path("post/novo/", PostCreateView.as_view(), name="create_post"),
    path("post/<int:pk>/editar/", PostEditView.as_view(), name="edit_post"),
    path("post/<int:pk>/excluir/", PostDeleteView.as_view(), name="delete_post"),
    path("post/<int:pk>/compartilhar/", SharePostView.as_view(), name="share_post"),
    path("post/<int:pk>/gerar-legenda/", GenerateCaptionView.as_view(), name="generate_caption"),
    path("post/<int:pk>/registrar-compartilhamento/", LogShareView.as_view(), name="log_share"),
    path("post/<int:pk>/baixar-imagem/", DownloadPostImageView.as_view(), name="download_post_image"),
    path("post/<int:pk>/curtir/", ToggleLikeView.as_view(), name="toggle_like"),
    path("post/<int:pk>/comentar/", AddCommentView.as_view(), name="add_comment"),
    path("comentario/<int:pk>/editar/", CommentEditView.as_view(), name="edit_comment"),
    path("comentario/<int:pk>/excluir/", CommentDeleteView.as_view(), name="delete_comment"),
    path("perfil/<int:user_id>/", ProfilePostsView.as_view(), name="profile"),
    path("notificacoes/lidas/", MarkNotificationsReadView.as_view(), name="mark_notifications_read"),
]
