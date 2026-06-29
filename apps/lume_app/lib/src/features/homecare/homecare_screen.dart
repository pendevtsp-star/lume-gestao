import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/mobile_models.dart';
import '../../services/api_client.dart';

class HomecareScreen extends StatefulWidget {
  const HomecareScreen({required this.apiClient, super.key});

  final ApiClient apiClient;

  @override
  State<HomecareScreen> createState() => _HomecareScreenState();
}

class _HomecareScreenState extends State<HomecareScreen> {
  late Future<HomecareLibrary> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<HomecareLibrary> _load() async {
    final payload = await widget.apiClient.getJson('/api/v1/mobile/homecare/');
    return HomecareLibrary.fromJson(payload);
  }

  Future<void> _reload() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _openVideo(HomecareVideo video) async {
    final payload = await widget.apiClient.getJson('/api/v1/mobile/homecare/videos/${video.slug}/');
    if (!mounted) {
      return;
    }
    final detailed = HomecareVideo.fromJson(payload['video'] as Map<String, dynamic>? ?? {});
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (sheetContext) {
        return _VideoSheet(
          video: detailed,
          onOpen: detailed.embedUrl.isEmpty
              ? null
              : () async {
                  final uri = Uri.parse(detailed.embedUrl);
                  if (await canLaunchUrl(uri)) {
                    await launchUrl(uri, mode: LaunchMode.externalApplication);
                  }
                },
          onComplete: () async {
            await widget.apiClient.postJson(
              '/api/v1/mobile/homecare/videos/${detailed.slug}/progress/',
              body: {'completed': true, 'watched_seconds': 999999},
            );
            if (mounted && sheetContext.mounted) {
              Navigator.of(sheetContext).pop();
              await _reload();
            }
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _reload,
      child: FutureBuilder<HomecareLibrary>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _HomecareFailure(message: snapshot.error.toString(), onRetry: _reload);
          }
          final library = snapshot.requireData;
          if (!library.enabled) {
            return const _HomecareEmpty(text: 'Fisioterapia em Casa ainda nao esta habilitado.');
          }
          if (!library.hasAccess) {
            return _NoAccess(plans: library.plans);
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              _SubscriptionHeader(subscription: library.subscription),
              if (library.continueWatching.isNotEmpty) ...[
                const SizedBox(height: 16),
                const _SectionTitle(title: 'Continuar assistindo'),
                const SizedBox(height: 8),
                for (final video in library.continueWatching)
                  _VideoTile(video: video, onTap: () => _openVideo(video)),
              ],
              const SizedBox(height: 16),
              const _SectionTitle(title: 'Biblioteca'),
              const SizedBox(height: 8),
              if (library.videos.isEmpty)
                const _HomecareEmpty(text: 'Nenhum video publicado ainda.')
              else
                for (final video in library.videos)
                  _VideoTile(video: video, onTap: () => _openVideo(video)),
            ],
          );
        },
      ),
    );
  }
}

class _SubscriptionHeader extends StatelessWidget {
  const _SubscriptionHeader({this.subscription});

  final HomecareSubscription? subscription;

  @override
  Widget build(BuildContext context) {
    final expiresAt = subscription?.currentPeriodEnd;
    final subtitle = expiresAt == null
        ? subscription?.statusLabel ?? 'Acesso ativo'
        : 'Acesso ate ${DateFormat('dd/MM/yyyy').format(expiresAt)}';
    return Card(
      child: ListTile(
        leading: const Icon(Icons.home_work_outlined),
        title: Text(subscription?.plan ?? 'Fisioterapia em Casa'),
        subtitle: Text(subtitle),
      ),
    );
  }
}

class _VideoTile extends StatelessWidget {
  const _VideoTile({required this.video, required this.onTap});

  final HomecareVideo video;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        onTap: onTap,
        leading: video.thumbnailUrl.isEmpty
            ? const CircleAvatar(child: Icon(Icons.play_arrow))
            : ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(video.thumbnailUrl, width: 56, height: 56, fit: BoxFit.cover),
              ),
        title: Text(video.title, maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: Text('${video.category} | ${video.difficultyLabel} | ${video.durationLabel}'),
        trailing: video.completed
            ? const Icon(Icons.check_circle, color: Color(0xFF0F766E))
            : Text('${video.progressPercent}%'),
      ),
    );
  }
}

class _VideoSheet extends StatelessWidget {
  const _VideoSheet({
    required this.video,
    required this.onComplete,
    this.onOpen,
  });

  final HomecareVideo video;
  final VoidCallback? onOpen;
  final Future<void> Function() onComplete;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(20, 8, 20, MediaQuery.of(context).viewInsets.bottom + 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(video.title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text('${video.author} | ${video.category} | ${video.durationLabel}'),
            if (video.description.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(video.description),
            ],
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: onOpen,
                    icon: const Icon(Icons.play_circle_outline),
                    label: const Text('Abrir video'),
                  ),
                ),
                const SizedBox(width: 10),
                IconButton.filledTonal(
                  tooltip: 'Marcar concluido',
                  onPressed: onComplete,
                  icon: const Icon(Icons.check),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _NoAccess extends StatelessWidget {
  const _NoAccess({required this.plans});

  final List<HomecarePlan> plans;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        const Card(
          child: ListTile(
            leading: Icon(Icons.lock_outline),
            title: Text('Acesso ainda nao liberado'),
            subtitle: Text('Solicite a liberacao da assinatura pela clinica.'),
          ),
        ),
        const SizedBox(height: 16),
        const _SectionTitle(title: 'Planos disponiveis'),
        const SizedBox(height: 8),
        for (final plan in plans)
          Card(
            child: ListTile(
              title: Text(plan.name),
              subtitle: Text(plan.description.isEmpty ? plan.billingCycleLabel : plan.description),
              trailing: Text('R\$ ${plan.monthlyPrice}'),
            ),
          ),
      ],
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
    );
  }
}

class _HomecareEmpty extends StatelessWidget {
  const _HomecareEmpty({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const Icon(Icons.video_library_outlined, size: 42),
        const SizedBox(height: 12),
        Text(text, textAlign: TextAlign.center),
      ],
    );
  }
}

class _HomecareFailure extends StatelessWidget {
  const _HomecareFailure({required this.message, required this.onRetry});

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
