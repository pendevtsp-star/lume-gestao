import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/mobile_models.dart';
import '../../services/api_client.dart';
import '../auth/auth_controller.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    required this.controller,
    required this.apiClient,
    super.key,
  });

  final AuthController controller;
  final ApiClient apiClient;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<DashboardSummary> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<DashboardSummary> _load() async {
    final payload = await widget.apiClient.getJson('/api/v1/mobile/bootstrap/');
    return DashboardSummary.fromJson(payload);
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Lume Gestao'),
        actions: [
          IconButton(
            tooltip: 'Atualizar',
            onPressed: _reload,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: 'Sair',
            onPressed: widget.controller.signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: FutureBuilder<DashboardSummary>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _FailureState(
              message: snapshot.error.toString(),
              onRetry: _reload,
            );
          }
          final summary = snapshot.requireData;
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              children: [
                _ProfileHeader(profile: summary.profile),
                const SizedBox(height: 16),
                if (summary.metrics.isNotEmpty) _MetricsGrid(metrics: summary.metrics),
                if (summary.weeklyCredits != null || summary.packageCredits != null) ...[
                  const SizedBox(height: 16),
                  _CreditsSection(
                    weekly: summary.weeklyCredits,
                    packageCredits: summary.packageCredits,
                  ),
                ],
                if (summary.nextPayment != null) ...[
                  const SizedBox(height: 16),
                  _PaymentCard(payment: summary.nextPayment!),
                ],
                const SizedBox(height: 16),
                _AppointmentsSection(appointments: summary.nextAppointments),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.profile});

  final UserProfile profile;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            CircleAvatar(
              radius: 28,
              child: Text(
                profile.initials,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    profile.displayName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    profile.roleLabel,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MetricsGrid extends StatelessWidget {
  const _MetricsGrid({required this.metrics});

  final List<DashboardMetric> metrics;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 720 ? 3 : 2;
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: metrics.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            childAspectRatio: columns == 3 ? 2.7 : 2.2,
          ),
          itemBuilder: (context, index) {
            final metric = metrics[index];
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      metric.value,
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      metric.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}

class _CreditsSection extends StatelessWidget {
  const _CreditsSection({this.weekly, this.packageCredits});

  final CreditsPreview? weekly;
  final CreditsPreview? packageCredits;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (weekly != null)
          Expanded(
            child: _CreditCard(
              title: 'Creditos da semana',
              total: weekly!.allowed,
              used: weekly!.used,
              remaining: weekly!.remaining,
            ),
          ),
        if (weekly != null && packageCredits != null) const SizedBox(width: 10),
        if (packageCredits != null)
          Expanded(
            child: _CreditCard(
              title: 'Pacote ativo',
              total: packageCredits!.total ?? 0,
              used: packageCredits!.used,
              remaining: packageCredits!.remaining,
            ),
          ),
      ],
    );
  }
}

class _CreditCard extends StatelessWidget {
  const _CreditCard({
    required this.title,
    required this.total,
    required this.used,
    required this.remaining,
  });

  final String title;
  final int total;
  final int used;
  final int remaining;

  @override
  Widget build(BuildContext context) {
    final progress = total <= 0 ? 0.0 : (used / total).clamp(0.0, 1.0);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 12),
            LinearProgressIndicator(value: progress),
            const SizedBox(height: 10),
            Text('$remaining restantes'),
          ],
        ),
      ),
    );
  }
}

class _PaymentCard extends StatelessWidget {
  const _PaymentCard({required this.payment});

  final PaymentPreview payment;

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('dd/MM/yyyy');
    return Card(
      child: ListTile(
        leading: const Icon(Icons.payments_outlined),
        title: Text(payment.plan),
        subtitle: Text(
          payment.dueDate == null ? payment.status : 'Vence em ${dateFormat.format(payment.dueDate!)}',
        ),
        trailing: Text(
          'R\$ ${payment.amount}',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}

class _AppointmentsSection extends StatelessWidget {
  const _AppointmentsSection({required this.appointments});

  final List<AppointmentPreview> appointments;

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('dd/MM HH:mm');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Proximos agendamentos',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 8),
            if (appointments.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('Nenhum agendamento futuro.'),
              )
            else
              for (final appointment in appointments)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.event_available_outlined),
                  title: Text(
                    appointment.patient ?? 'Atendimento',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    appointment.startsAt == null ? appointment.status : dateFormat.format(appointment.startsAt!),
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

class _FailureState extends StatelessWidget {
  const _FailureState({
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, size: 42),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }
}
