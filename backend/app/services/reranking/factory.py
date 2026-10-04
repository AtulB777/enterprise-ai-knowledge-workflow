from app.services.reranking.cross_encoder_reranker import CrossEncoderReranker
from app.services.reranking.reranker import Reranker


def get_reranker() -> Reranker:
    return CrossEncoderReranker()
