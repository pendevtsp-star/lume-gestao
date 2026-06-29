import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/mobile_models.dart';
import '../../services/api_client.dart';

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({required this.apiClient, super.key});

  final ApiClient apiClient;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  late Future<ConnectFeed> _future;
  final _postController = TextEditingController();
  bool _posting = false;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _postController.dispose();
    super.dispose();
  }

  Future<ConnectFeed> _load() async {
    final payload = await widget.apiClient.getJson('/api/v1/mobile/connect/');
    return ConnectFeed.fromJson(payload);
  }

  Future<void> _reload() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _publish() async {
    final content = _postController.text.trim();
    if (content.isEmpty || _posting) {
      return;
    }
    setState(() {
      _posting = true;
    });
    try {
      await widget.apiClient.postJson('/api/v1/mobile/connect/', body: {'content': content});
      _postController.clear();
      await _reload();
    } finally {
      if (mounted) {
        setState(() {
          _posting = false;
        });
      }
    }
  }

  Future<void> _toggleLike(ConnectPost post) async {
    await widget.apiClient.postJson('/api/v1/mobile/connect/${post.id}/like/');
    await _reload();
  }

  Future<void> _comment(ConnectPost post) async {
    final controller = TextEditingController();
    final content = await showDialog<String>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Comentar'),
          content: TextField(
            controller: controller,
            autofocus: true,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(labelText: 'Comentario'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(controller.text.trim()),
              child: const Text('Enviar'),
            ),
          ],
        );
      },
    );
    controller.dispose();
    if (content == null || content.isEmpty) {
      return;
    }
    await widget.apiClient.postJson(
      '/api/v1/mobile/connect/${post.id}/comments/',
      body: {'content': content},
    );
    await _reload();
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _reload,
      child: FutureBuilder<ConnectFeed>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _ConnectFailure(message: snapshot.error.toString(), onRetry: _reload);
          }
          final feed = snapshot.requireData;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              _Composer(
                controller: _postController,
                posting: _posting,
                onPublish: _publish,
              ),
              const SizedBox(height: 12),
              if (feed.unreadNotifications > 0)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _InfoBanner(text: '${feed.unreadNotifications} notificacoes novas'),
                ),
              if (feed.posts.isEmpty)
                const _InfoBanner(text: 'Nenhum post ainda.')
              else
                for (final post in feed.posts) ...[
                  _PostCard(
                    post: post,
                    onLike: () => _toggleLike(post),
                    onComment: () => _comment(post),
                  ),
                  const SizedBox(height: 12),
                ],
            ],
          );
        },
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.posting,
    required this.onPublish,
  });

  final TextEditingController controller;
  final bool posting;
  final VoidCallback onPublish;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Lume Connect', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              minLines: 2,
              maxLines: 5,
              decoration: const InputDecoration(
                hintText: 'Compartilhe um aviso, orientacao ou conquista...',
              ),
            ),
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.icon(
                onPressed: posting ? null : onPublish,
                icon: posting
                    ? const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.send_outlined),
                label: const Text('Publicar'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PostCard extends StatelessWidget {
  const _PostCard({
    required this.post,
    required this.onLike,
    required this.onComment,
  });

  final ConnectPost post;
  final VoidCallback onLike;
  final VoidCallback onComment;

  @override
  Widget build(BuildContext context) {
    final date = post.createdAt == null ? '' : DateFormat('dd/MM HH:mm').format(post.createdAt!);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(child: Text(post.authorInitials)),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(post.authorName, style: const TextStyle(fontWeight: FontWeight.w700)),
                      if (date.isNotEmpty) Text(date, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
                if (post.isPinned) const Icon(Icons.push_pin_outlined, size: 18),
              ],
            ),
            if (post.content.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(post.content),
            ],
            if (post.imageUrl.isNotEmpty) ...[
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(post.imageUrl, fit: BoxFit.cover),
              ),
            ],
            const SizedBox(height: 8),
            Row(
              children: [
                TextButton.icon(
                  onPressed: onLike,
                  icon: Icon(post.likedByMe ? Icons.favorite : Icons.favorite_border),
                  label: Text('${post.likesCount}'),
                ),
                TextButton.icon(
                  onPressed: onComment,
                  icon: const Icon(Icons.mode_comment_outlined),
                  label: Text('${post.commentsCount}'),
                ),
              ],
            ),
            if (post.recentComments.isNotEmpty) ...[
              const Divider(),
              for (final comment in post.recentComments)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: '${comment.authorName}: ',
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        TextSpan(text: comment.content),
                      ],
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _InfoBanner extends StatelessWidget {
  const _InfoBanner({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(text),
      ),
    );
  }
}

class _ConnectFailure extends StatelessWidget {
  const _ConnectFailure({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const Icon(Icons.cloud_off_outlined, size: 42),
        const SizedBox(height: 12),
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
          label: const Text('Tentar novamente'),
        ),
      ],
    );
  }
}
