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

class ConnectFeed {
  const ConnectFeed({
    required this.unreadNotifications,
    required this.posts,
  });

  factory ConnectFeed.fromJson(Map<String, dynamic> json) {
    return ConnectFeed(
      unreadNotifications: json['unread_notifications'] as int? ?? 0,
      posts: (json['posts'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(ConnectPost.fromJson)
          .toList(growable: false),
    );
  }

  final int unreadNotifications;
  final List<ConnectPost> posts;
}

class ConnectPost {
  const ConnectPost({
    required this.id,
    required this.content,
    required this.authorName,
    required this.authorInitials,
    required this.createdAt,
    required this.likesCount,
    required this.commentsCount,
    required this.likedByMe,
    required this.recentComments,
    this.imageUrl = '',
    this.isPinned = false,
    this.isAnnouncement = false,
  });

  factory ConnectPost.fromJson(Map<String, dynamic> json) {
    return ConnectPost(
      id: json['id'] as int? ?? 0,
      content: json['content'] as String? ?? '',
      imageUrl: json['image_url'] as String? ?? '',
      authorName: json['author_name'] as String? ?? '',
      authorInitials: json['author_initials'] as String? ?? 'U',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
      likesCount: json['likes_count'] as int? ?? 0,
      commentsCount: json['comments_count'] as int? ?? 0,
      likedByMe: json['liked_by_me'] as bool? ?? false,
      isPinned: json['is_pinned'] as bool? ?? false,
      isAnnouncement: json['is_announcement'] as bool? ?? false,
      recentComments: (json['recent_comments'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(ConnectComment.fromJson)
          .toList(growable: false),
    );
  }

  final int id;
  final String content;
  final String imageUrl;
  final String authorName;
  final String authorInitials;
  final DateTime? createdAt;
  final int likesCount;
  final int commentsCount;
  final bool likedByMe;
  final bool isPinned;
  final bool isAnnouncement;
  final List<ConnectComment> recentComments;
}

class ConnectComment {
  const ConnectComment({
    required this.id,
    required this.content,
    required this.authorName,
    required this.authorInitials,
    required this.createdAt,
  });

  factory ConnectComment.fromJson(Map<String, dynamic> json) {
    return ConnectComment(
      id: json['id'] as int? ?? 0,
      content: json['content'] as String? ?? '',
      authorName: json['author_name'] as String? ?? '',
      authorInitials: json['author_initials'] as String? ?? 'U',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
    );
  }

  final int id;
  final String content;
  final String authorName;
  final String authorInitials;
  final DateTime? createdAt;
}

class HomecareLibrary {
  const HomecareLibrary({
    required this.enabled,
    required this.hasAccess,
    required this.plans,
    required this.categories,
    required this.videos,
    required this.continueWatching,
    this.subscription,
  });

  factory HomecareLibrary.fromJson(Map<String, dynamic> json) {
    return HomecareLibrary(
      enabled: json['enabled'] as bool? ?? false,
      hasAccess: json['has_access'] as bool? ?? false,
      subscription: json['subscription'] is Map<String, dynamic>
          ? HomecareSubscription.fromJson(json['subscription'] as Map<String, dynamic>)
          : null,
      plans: (json['plans'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(HomecarePlan.fromJson)
          .toList(growable: false),
      categories: (json['categories'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(HomecareCategory.fromJson)
          .toList(growable: false),
      videos: (json['videos'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(HomecareVideo.fromJson)
          .toList(growable: false),
      continueWatching: (json['continue_watching'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(HomecareVideo.fromJson)
          .toList(growable: false),
    );
  }

  final bool enabled;
  final bool hasAccess;
  final HomecareSubscription? subscription;
  final List<HomecarePlan> plans;
  final List<HomecareCategory> categories;
  final List<HomecareVideo> videos;
  final List<HomecareVideo> continueWatching;
}

class HomecareSubscription {
  const HomecareSubscription({
    required this.plan,
    required this.statusLabel,
    this.currentPeriodEnd,
  });

  factory HomecareSubscription.fromJson(Map<String, dynamic> json) {
    return HomecareSubscription(
      plan: json['plan'] as String? ?? '',
      statusLabel: json['status_label'] as String? ?? '',
      currentPeriodEnd: DateTime.tryParse(json['current_period_end'] as String? ?? ''),
    );
  }

  final String plan;
  final String statusLabel;
  final DateTime? currentPeriodEnd;
}

class HomecarePlan {
  const HomecarePlan({
    required this.name,
    required this.description,
    required this.monthlyPrice,
    required this.billingCycleLabel,
  });

  factory HomecarePlan.fromJson(Map<String, dynamic> json) {
    return HomecarePlan(
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      monthlyPrice: json['monthly_price'] as String? ?? '',
      billingCycleLabel: json['billing_cycle_label'] as String? ?? '',
    );
  }

  final String name;
  final String description;
  final String monthlyPrice;
  final String billingCycleLabel;
}

class HomecareCategory {
  const HomecareCategory({
    required this.name,
    required this.slug,
    required this.description,
  });

  factory HomecareCategory.fromJson(Map<String, dynamic> json) {
    return HomecareCategory(
      name: json['name'] as String? ?? '',
      slug: json['slug'] as String? ?? '',
      description: json['description'] as String? ?? '',
    );
  }

  final String name;
  final String slug;
  final String description;
}

class HomecareVideo {
  const HomecareVideo({
    required this.id,
    required this.title,
    required this.slug,
    required this.description,
    required this.category,
    required this.author,
    required this.difficultyLabel,
    required this.durationLabel,
    required this.progressPercent,
    required this.completed,
    this.thumbnailUrl = '',
    this.embedUrl = '',
  });

  factory HomecareVideo.fromJson(Map<String, dynamic> json) {
    return HomecareVideo(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      slug: json['slug'] as String? ?? '',
      description: json['description'] as String? ?? '',
      category: json['category'] as String? ?? '',
      author: json['author'] as String? ?? '',
      difficultyLabel: json['difficulty_label'] as String? ?? '',
      durationLabel: json['duration_label'] as String? ?? '',
      progressPercent: json['progress_percent'] as int? ?? 0,
      completed: json['completed'] as bool? ?? false,
      thumbnailUrl: json['thumbnail_url'] as String? ?? '',
      embedUrl: json['embed_url'] as String? ?? '',
    );
  }

  final int id;
  final String title;
  final String slug;
  final String description;
  final String category;
  final String author;
  final String difficultyLabel;
  final String durationLabel;
  final int progressPercent;
  final bool completed;
  final String thumbnailUrl;
  final String embedUrl;
}
