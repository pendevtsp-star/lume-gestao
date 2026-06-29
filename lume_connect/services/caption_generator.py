import random

from django.conf import settings


HASHTAGS = [
    "#StudioLume",
    "#Fisioterapia",
    "#Movimento",
    "#BemEstar",
    "#CuidadoComMovimento",
    "#Pilates",
    "#SaudeComCuidado",
]

FORBIDDEN_PHRASES = [
    "cura garantida",
    "resultado garantido",
    "tratamento milagroso",
    "diagnostico",
    "diagnostico garantido",
]


def advanced_caption_enabled():
    return bool(
        getattr(settings, "AI_CAPTION_ENABLED", False)
        and getattr(settings, "AI_PROVIDER", "")
        and getattr(settings, "AI_API_KEY", "")
        and getattr(settings, "AI_CAPTION_MODEL", "")
    )


def caption_prompt(post, image_description=""):
    post_text = (post.content or "").strip() or "Post com imagem no Lume Connect."
    return (
        "Voce e um assistente de comunicacao para um studio de fisioterapia chamado Studio Lume. "
        "Crie uma legenda curta, humana, acolhedora e profissional para uma publicacao no Instagram "
        "feita por um paciente/usuario. Use o conteudo do post e, se disponivel, a descricao da imagem. "
        "Nao faca diagnostico, nao prometa cura, nao cite dados clinicos sensiveis e nao invente informacoes. "
        "A legenda deve valorizar movimento, cuidado, bem-estar e evolucao. Inclua uma referencia natural ao "
        "Studio Lume e ate 5 hashtags relevantes. Entregue apenas a legenda final, pronta para edicao pelo usuario.\n\n"
        f"Post original: {post_text}\n"
        f"Descricao segura da imagem: {image_description or 'Nao configurada nesta versao.'}"
    )


def sanitize_caption(caption):
    cleaned = " ".join((caption or "").split())
    for phrase in FORBIDDEN_PHRASES:
        cleaned = cleaned.replace(phrase, "")
        cleaned = cleaned.replace(phrase.title(), "")
    return cleaned.strip()


def local_caption(post):
    post_text = sanitize_caption((post.content or "").strip())
    seed = f"{post.pk}:{post.created_at:%Y%m%d%H%M%S}" if post.pk and post.created_at else post_text
    rng = random.Random(seed)
    openings = [
        "Um registro de movimento, cuidado e presenca.",
        "Cada passo da rotina tambem pode ser um gesto de cuidado.",
        "Celebrando os pequenos avancos que fazem parte do caminho.",
        "Movimento com atencao, escuta e leveza.",
    ]
    bridges = [
        "No Studio Lume, o cuidado acontece com respeito ao ritmo de cada pessoa.",
        "O Studio Lume acredita em evolucao com consciencia, acolhimento e constancia.",
        "No Studio Lume, bem-estar e movimento caminham juntos.",
    ]
    selected_tags = " ".join(rng.sample(HASHTAGS, 5))
    original = f"\n\nSobre o momento: {post_text}" if post_text else ""
    return sanitize_caption(f"{rng.choice(openings)}{original}\n\n{rng.choice(bridges)}\n\n{selected_tags}")


def generate_caption(post, image_description=""):
    # The advanced provider hook is intentionally isolated for a future Meta/OpenAI review.
    # Version 0.2.0 keeps the feature safe with a local fallback and no automatic publishing.
    prompt = caption_prompt(post, image_description=image_description)
    fallback = local_caption(post)
    if advanced_caption_enabled():
        return {
            "caption": fallback,
            "source": "local_fallback",
            "message": (
                "A configuracao de IA foi detectada, mas a integracao avancada de legenda ainda esta reservada "
                "para uma etapa futura. Voce pode editar a sugestao abaixo."
            ),
            "prompt": prompt,
        }
    return {
        "caption": fallback,
        "source": "local_fallback",
        "message": "A geracao automatica avancada ainda nao esta configurada. Voce pode editar a sugestao abaixo.",
        "prompt": prompt,
    }
