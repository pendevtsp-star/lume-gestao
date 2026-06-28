class AppConfig {
  static const apiBaseUrl = String.fromEnvironment(
    'LUME_API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const allowInsecureHttp = bool.fromEnvironment(
    'LUME_ALLOW_INSECURE_HTTP',
    defaultValue: true,
  );

  static Uri apiUri(String path) {
    final base = Uri.parse(apiBaseUrl);
    final isLocalDev = {
      'localhost',
      '127.0.0.1',
      '10.0.2.2',
    }.contains(base.host);

    if (base.scheme != 'https' && !allowInsecureHttp && !isLocalDev) {
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
