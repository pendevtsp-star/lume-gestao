export function messageIdFromSendResult(sent) {
  return sent?.id?._serialized || "";
}
