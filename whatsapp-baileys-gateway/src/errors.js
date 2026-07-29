export class ProviderError extends Error {
  constructor(message, {
    code = "PROVIDER_ERROR",
    retryable = false,
    deliveryUncertain = false,
    httpStatus = 500
  } = {}) {
    super(message);
    this.name = "ProviderError";
    this.code = code;
    this.deliveryUncertain = Boolean(deliveryUncertain);
    this.retryable = this.deliveryUncertain ? false : Boolean(retryable);
    this.httpStatus = httpStatus;
  }
}

export function errorPayload(error) {
  const providerError = error instanceof ProviderError
    ? error
    : new ProviderError("Falha interna no gateway.");
  return {
    ok: false,
    code: providerError.code,
    retryable: providerError.retryable,
    deliveryUncertain: providerError.deliveryUncertain,
    error: providerError.message
  };
}
