# Search images

Web searches retrieve supplementary images through Serper, with the configured
Tavily provider as a fallback when Serper is missing, rejects access, times out,
returns an invalid response, or returns no usable images. Tavily's basic search
requests `include_images`; the response adapter supports both top-level images
and images associated with result pages, retaining real source links where provided.
[Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search).

Provider attempts have wall-time limits within the image tool's ten-second budget.
Rejections and rate limits have bounded cooldowns scoped to credential fingerprints.
Successful image results have a five-minute process cache capped at 64 entries.
Cancellation propagates; supplementary failures do not discard the text answer.
Response size is capped at 2 MB and image count at 20. Only public HTTPS image URLs
are accepted; invalid, duplicate, credential-bearing and local-address URLs are removed.
Logs exclude provider keys and response bodies. Both providers retain their normal
quotas: a Tavily fallback is an additional basic search request.

The gallery retries a failed thumbnail using the original image. The lightbox tries
the preview if the original cannot load. Exhausted links show “Image unavailable”
instead of silently hiding every card. Remote requests omit the browser referrer.
Previously saved answers retain their saved image arrays; a new web search retrieves
images through the corrected pipeline. Greetings, conversation-only answers and
file-only searches do not promise web images.

Tests cover rejection, fallback-only configuration, empty results versus outages,
malformed/oversized responses, timeout, cancellation, credential changes, URL safety,
deduplication, source attribution and client candidate order. This change does not
modify Space agents, API keys or hosting capacity.
