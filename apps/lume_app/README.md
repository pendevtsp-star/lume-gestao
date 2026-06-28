# Lume App

Cliente Flutter para Android e macOS consumindo a API mobile do Django.

## Preparar ambiente

Instale o Flutter SDK e confira:

```powershell
flutter doctor
```

Depois gere os arquivos nativos dentro desta pasta. Em Windows, incluir `windows` ajuda a testar o app localmente; o alvo de publicacao continua Android e macOS.

```powershell
cd apps/lume_app
flutter create --platforms=android,macos,windows .
flutter pub get
```

## Rodar em desenvolvimento

Com o backend Django em `http://127.0.0.1:8000`:

```powershell
flutter run -d windows --dart-define=LUME_API_BASE_URL=http://127.0.0.1:8000
```

Para emulador Android, use o host especial do emulador:

```powershell
flutter run -d android --dart-define=LUME_API_BASE_URL=http://10.0.2.2:8000
```

O build macOS final precisa ser feito em um Mac.

Para producao, use sempre HTTPS:

```powershell
flutter build appbundle --dart-define=LUME_API_BASE_URL=https://sistema.clinicafisiolume.com.br --dart-define=LUME_ALLOW_INSECURE_HTTP=false
flutter build macos --dart-define=LUME_API_BASE_URL=https://sistema.clinicafisiolume.com.br --dart-define=LUME_ALLOW_INSECURE_HTTP=false
```

## Estado atual

- Login via `/api/v1/mobile/auth/login/`.
- Token salvo em armazenamento seguro do sistema.
- Dashboard inicial via `/api/v1/mobile/bootstrap/`.
- Logout revoga o token em `/api/v1/mobile/auth/logout/`.

Proxima etapa tecnica: trocar token simples por access/refresh token com expiracao curta e controle por dispositivo no backend.
