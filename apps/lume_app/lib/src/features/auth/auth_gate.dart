import 'package:flutter/material.dart';

import '../../features/dashboard/dashboard_screen.dart';
import '../../services/api_client.dart';
import 'auth_controller.dart';
import 'login_screen.dart';

class AuthGate extends StatelessWidget {
  const AuthGate({
    required this.controller,
    required this.apiClient,
    super.key,
  });

  final AuthController controller;
  final ApiClient apiClient;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        switch (controller.status) {
          case AuthStatus.checking:
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          case AuthStatus.signedIn:
            return DashboardScreen(
              controller: controller,
              apiClient: apiClient,
            );
          case AuthStatus.signedOut:
            return LoginScreen(controller: controller);
        }
      },
    );
  }
}
