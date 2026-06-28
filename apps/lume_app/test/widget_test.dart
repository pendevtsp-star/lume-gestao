import 'package:flutter_test/flutter_test.dart';
import 'package:lume_app/src/config/app_config.dart';

void main() {
  test('builds API URLs from the configured base URL', () {
    final uri = AppConfig.apiUri('/api/v1/mobile/bootstrap/');

    expect(uri.toString(), 'http://127.0.0.1:8000/api/v1/mobile/bootstrap');
  });
}
