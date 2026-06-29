class AppConfig {
  static const appVersion = '0.2.3';
  static const productionApiBaseUrl = 'https://sistema.clinicafisiolume.com.br';

  static const apiBaseUrl = String.fromEnvironment(
    'LUME_API_BASE_URL',
    defaultValue: productionApiBaseUrl,
  );

  static const allowInsecureHttp = bool.fromEnvironment(
    'LUME_ALLOW_INSECURE_HTTP',
    defaultValue: false,
  );

  static Uri apiUri(String path) {
    final base = Uri.parse(apiBaseUrl);

    if (base.scheme != 'https' && !allowInsecureHttp) {
      throw StateError('A API de producao precisa usar HTTPS.');
    }

    final normalizedPath = path.startsWith('/') ? path.substring(1) : path;
    return base.replace(
      pathSegments: [
        ...base.pathSegments.where((segment) => segment.isNotEmpty),
        ...normalizedPath.split('/').where((segment) => segment.isNotEmpty),
      ],
    );
  }
}
