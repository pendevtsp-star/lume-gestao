# Lume App

**Status: projeto pausado temporariamente.**

Cliente Flutter para Android e iOS consumindo a API mobile do Django.

## Estado no monorepo

Este aplicativo faz parte da estrategia futura do Lume, mas o desenvolvimento esta pausado temporariamente.
Ele permanece versionado em `apps/lume_app/` para preservar o codigo-fonte, porem nao participa do build, do deploy da VPS nem dos workflows da aplicacao web em producao.

Quando o mobile for retomado, o ideal e criar um workflow proprio, separado do deploy web, para validar Flutter, gerar APK/AAB e publicar artefatos.

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

Para instalar APK direto em um celular na mesma rede, use o IP da maquina/servidor que roda o Django:

```powershell
flutter build apk --release --dart-define=LUME_API_BASE_URL=http://192.168.0.50:8000
```

Ou, pela raiz do projeto:

```powershell
.\scripts\build-apk.ps1 -ApiBaseUrl "http://192.168.0.50:8000" -AllowInsecureHttp
```

Para gerar apontando para o servidor HTTPS padrao:

```powershell
.\scripts\build-apk.ps1
```

O APK sai em:

```text
build/app/outputs/flutter-apk/app-release.apk
```

Esse APK pode ser distribuido manualmente, sem Play Store. No Android, habilite a instalacao de apps da origem usada para abrir o arquivo.

O build iOS final precisa ser feito em um Mac.

Para producao, use sempre HTTPS:

```powershell
flutter build appbundle --dart-define=LUME_API_BASE_URL=https://sistema.clinicafisiolume.com.br --dart-define=LUME_ALLOW_INSECURE_HTTP=false
flutter build macos --dart-define=LUME_API_BASE_URL=https://sistema.clinicafisiolume.com.br --dart-define=LUME_ALLOW_INSECURE_HTTP=false
```

## Estado atual

- Login via `/api/v1/mobile/auth/login/`.
- Token salvo em armazenamento seguro do sistema.
- Dashboard inicial via `/api/v1/mobile/bootstrap/`.
- Lume Connect via `/api/v1/mobile/connect/`: feed, publicacao textual, curtidas e comentarios.
- Logout revoga o token em `/api/v1/mobile/auth/logout/`.

Proxima etapa tecnica: trocar token simples por access/refresh token com expiracao curta e controle por dispositivo no backend.
