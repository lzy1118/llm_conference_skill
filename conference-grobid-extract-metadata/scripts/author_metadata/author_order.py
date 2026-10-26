def get_export_author_rank(author, authors):
    """Export co-first authors at rank zero while preserving later order."""
    if author.get("co_first_author"):
        return 0
    co_first_count = sum(1 for item in authors if item.get("co_first_author"))
    if co_first_count > 1:
        return 1 + sum(
            1
            for item in authors
            if item.get("order", 0) < author.get("order", 0)
            and not item.get("co_first_author")
        )
    return author["order"]
