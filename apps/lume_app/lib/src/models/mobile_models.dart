class UserProfile {
  const UserProfile({
    required this.username,
    required this.displayName,
    required this.role,
    required this.roleLabel,
    required this.initials,
    this.avatarUrl = '',
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      username: json['username'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      role: json['role'] as String? ?? '',
      roleLabel: json['role_label'] as String? ?? '',
      initials: json['initials'] as String? ?? 'U',
      avatarUrl: json['avatar_url'] as String? ?? '',
    );
  }

  final String username;
  final String displayName;
  final String role;
  final String roleLabel;
  final String initials;
  final String avatarUrl;
}

class MobileSession {
  const MobileSession({
    required this.token,
    required this.profile,
    required this.features,
  });

  factory MobileSession.fromJson(Map<String, dynamic> json) {
    return MobileSession(
      token: json['token'] as String? ?? '',
      profile: UserProfile.fromJson(json['profile'] as Map<String, dynamic>? ?? {}),
      features: (json['features'] as List<dynamic>? ?? const [])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  final String token;
  final UserProfile profile;
  final List<String> features;
}

class DashboardSummary {
  const DashboardSummary({
    required this.profile,
    required this.features,
    required this.metrics,
    required this.nextAppointments,
    this.nextPayment,
    this.weeklyCredits,
    this.packageCredits,
  });

  factory DashboardSummary.fromJson(Map<String, dynamic> json) {
    final dashboard = json['dashboard'] as Map<String, dynamic>? ?? {};
    final metrics = <DashboardMetric>[];

    void addMetric(String key, String label) {
      final value = dashboard[key];
      if (value != null) {
        metrics.add(DashboardMetric(label: label, value: value.toString()));
      }
    }

    addMetric('active_patients', 'Pacientes ativos');
    addMetric('active_professionals', 'Profissionais');
    addMetric('employees', 'Equipe ativa');
    addMetric('upcoming_appointments', 'Agenda futura');
    addMetric('pending_payments', 'Pagamentos pendentes');
    addMetric('assigned_patients', 'Pacientes vinculados');

    return DashboardSummary(
      profile: UserProfile.fromJson(json['profile'] as Map<String, dynamic>? ?? {}),
      features: (json['features'] as List<dynamic>? ?? const [])
          .whereType<String>()
          .toList(growable: false),
      metrics: metrics,
      nextAppointments: (dashboard['next_appointments'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(AppointmentPreview.fromJson)
          .toList(growable: false),
      nextPayment: dashboard['next_payment'] is Map<String, dynamic>
          ? PaymentPreview.fromJson(dashboard['next_payment'] as Map<String, dynamic>)
          : null,
      weeklyCredits: dashboard['weekly_credits'] is Map<String, dynamic>
          ? CreditsPreview.fromJson(dashboard['weekly_credits'] as Map<String, dynamic>)
          : null,
      packageCredits: dashboard['package_credits'] is Map<String, dynamic>
          ? CreditsPreview.fromJson(dashboard['package_credits'] as Map<String, dynamic>)
          : null,
    );
  }

  final UserProfile profile;
  final List<String> features;
  final List<DashboardMetric> metrics;
  final List<AppointmentPreview> nextAppointments;
  final PaymentPreview? nextPayment;
  final CreditsPreview? weeklyCredits;
  final CreditsPreview? packageCredits;
}

class DashboardMetric {
  const DashboardMetric({required this.label, required this.value});

  final String label;
  final String value;
}

class AppointmentPreview {
  const AppointmentPreview({
    required this.startsAt,
    required this.status,
    this.patient,
  });

  factory AppointmentPreview.fromJson(Map<String, dynamic> json) {
    return AppointmentPreview(
      startsAt: DateTime.tryParse(json['starts_at'] as String? ?? ''),
      status: json['status'] as String? ?? '',
      patient: json['patient'] as String?,
    );
  }

  final DateTime? startsAt;
  final String status;
  final String? patient;
}

class PaymentPreview {
  const PaymentPreview({
    required this.plan,
    required this.dueDate,
    required this.amount,
    required this.status,
  });

  factory PaymentPreview.fromJson(Map<String, dynamic> json) {
    return PaymentPreview(
      plan: json['plan'] as String? ?? '',
      dueDate: DateTime.tryParse(json['due_date'] as String? ?? ''),
      amount: json['amount'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }

  final String plan;
  final DateTime? dueDate;
  final String amount;
  final String status;
}

class CreditsPreview {
  const CreditsPreview({
    required this.allowed,
    required this.used,
    required this.remaining,
    this.total,
  });

  factory CreditsPreview.fromJson(Map<String, dynamic> json) {
    return CreditsPreview(
      allowed: json['allowed'] as int? ?? 0,
      total: json['total'] as int?,
      used: json['used'] as int? ?? 0,
      remaining: json['remaining'] as int? ?? 0,
    );
  }

  final int allowed;
  final int? total;
  final int used;
  final int remaining;
}
