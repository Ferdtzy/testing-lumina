# Model data untuk app documents sudah didefinisikan di core.models.
# App documents hanya berisi serializers, views, dan urls untuk API dokumen.
# Import model dari core untuk memudahkan referensi.
from core.models import Document, Chunk, IngestLog  # noqa: F401