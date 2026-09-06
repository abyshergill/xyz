from django.urls import get_resolver

def list_urls(resolver, prefix=""):
    for p in resolver.url_patterns:
        if hasattr(p, "url_patterns"):
            list_urls(p, prefix + str(p.pattern))
        else:
            print(f"{prefix}{p.pattern}  ->  name={p.name!r}")

list_urls(get_resolver())