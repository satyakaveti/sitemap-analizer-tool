from dataclasses import dataclass, field
from typing import Optional


@dataclass
class URLResult:
    url: str
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    redirect_count: int = 0
    redirect_chain: list[str] = field(default_factory=list)
    response_time: float = 0.0
    content_type: str = ""
    content_length: int = 0
    error: str = ""
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    h1: str = ""
    h1_count: int = 0
    word_count: int = 0
    canonical: str = ""
    robots: str = ""
    indexable: bool = True
    issues: list[dict] = field(default_factory=list)
    raw_html: Optional[bytes] = field(default=None, repr=False)
    score: int = 0
    score_rating: str = ""
    internal_link_count: int = 0
    external_link_count: int = 0
    broken_link_count: int = 0
    image_count: int = 0
    image_no_alt_count: int = 0
