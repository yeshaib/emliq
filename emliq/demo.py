"""A made-up mailbox for trying emliq without a Google account (`emliq demo`).

All senders, subjects and numbers are fictional. Actions that would touch Gmail are
disabled in demo mode; everything else (views, search, Ask AI, activity) works.
"""
from __future__ import annotations

import random
import time

from . import analytics
from .db import label_columns, set_meta

DEMO_EMAIL = "you@example.com"

# (name, address, category, suggestion, gmail category, mailing list?, messages, read share, subjects)
SENDERS = [
    ("Northwind Outfitters", "deals@news.northwind.example", "Shopping & deals", "unsubscribe", "CATEGORY_PROMOTIONS", True, 164, .02,
     ["Flash sale: 40% off trail gear", "Your weekend picks are here", "Last chance: free shipping ends tonight"]),
    ("Fabrikam Travel", "offers@fabrikam-travel.example", "Travel", "unsubscribe", "CATEGORY_PROMOTIONS", True, 121, .05,
     ["Fares to Lisbon from $389", "Your points are waiting", "48-hour hotel sale"]),
    ("Contoso Bank", "alerts@contoso-bank.example", "Finance & banking", "archive", "CATEGORY_UPDATES", False, 118, .6,
     ["Your statement is ready", "A payment was posted to your account", "Card ending 4417: purchase alert"]),
    ("The Daily Brief", "hello@dailybrief.example", "Newsletters", "unsubscribe", "CATEGORY_UPDATES", True, 142, .08,
     ["Morning Brief: 5 things to know", "The week in review", "Your Sunday long read"]),
    ("Acme Deals", "promo@acmedeals.example", "Shopping & deals", "unsubscribe", "CATEGORY_PROMOTIONS", True, 97, 0.0,
     ["Today only: doorbusters", "You left something in your cart", "Members save an extra 15%"]),
    ("Parcel Tracking", "noreply@parceltrack.example", "Orders & receipts", "archive", "CATEGORY_UPDATES", False, 88, .7,
     ["Your package is out for delivery", "Delivered: order #{n}", "Shipping update for order #{n}"]),
    ("Linkly", "notifications@linkly.example", "Social media", "unsubscribe", "CATEGORY_SOCIAL", True, 131, .03,
     ["You appeared in {n} searches this week", "New jobs that match your profile", "3 people viewed your profile"]),
    ("Blue Yonder Airlines", "trips@blueyonder.example", "Travel", "keep", "CATEGORY_UPDATES", False, 22, .9,
     ["Your trip to Denver: check in now", "Itinerary receipt", "Gate change for flight BY{n}"]),
    ("Tailspin Streaming", "account@tailspin.example", "Services & utilities", "archive", "CATEGORY_UPDATES", False, 36, .5,
     ["Your monthly receipt", "New this week on Tailspin", "Payment method expiring soon"]),
    ("City Power & Light", "billing@citypower.example", "Services & utilities", "archive", "CATEGORY_UPDATES", False, 30, .8,
     ["Your bill is ready", "Autopay scheduled", "Planned outage notice"]),
    ("Maria Lopez", "maria.lopez@example.com", "Personal", "keep", "CATEGORY_PERSONAL", False, 41, .95,
     ["Dinner Saturday?", "Photos from the trip", "Re: birthday plans"]),
    ("Sam Chen", "sam@example.net", "Work", "keep", "CATEGORY_PERSONAL", False, 57, .9,
     ["Draft for review", "Re: Q3 planning", "Notes from today's call"]),
    ("Litware Security", "security@litware.example", "Account & security", "keep", "CATEGORY_UPDATES", False, 19, .85,
     ["New sign-in from Chrome on Mac", "Your verification code", "Password changed"]),
    ("Adatum Careers", "jobs@adatum-careers.example", "Jobs & career", "unsubscribe", "CATEGORY_PROMOTIONS", True, 76, .04,
     ["12 new jobs for you", "Salary insights for your role", "Recruiters are looking"]),
    ("Wide World News", "newsletter@wwnews.example", "News & media", "unsubscribe", "CATEGORY_UPDATES", True, 109, .1,
     ["Breaking: markets close higher", "Your evening edition", "Opinion: the week ahead"]),
    ("Proseware Store", "orders@proseware.example", "Orders & receipts", "archive", "CATEGORY_UPDATES", False, 34, .6,
     ["Order confirmation #{n}", "Your receipt from Proseware", "Rate your recent purchase"]),
    ("Graphic Kitchen", "recipes@graphickitchen.example", "Newsletters", "unsubscribe", "CATEGORY_PROMOTIONS", True, 68, .0,
     ["5 dinners in 30 minutes", "This week's meal plan", "Soup season is here"]),
    ("Coho Fitness", "team@cohofitness.example", "Shopping & deals", "unsubscribe", "CATEGORY_PROMOTIONS", True, 58, .02,
     ["Your free week is waiting", "New classes this month", "Members-only sale"]),
    ("Trey Research", "digest@treyresearch.example", "Newsletters", "archive", "CATEGORY_UPDATES", True, 45, .35,
     ["Research digest #{n}", "New paper you might like", "Monthly highlights"]),
    ("Alpine Ski House", "info@alpineskihouse.example", "Shopping & deals", "unsubscribe", "CATEGORY_PROMOTIONS", True, 52, 0.0,
     ["Season passes on sale", "Fresh snow this weekend", "Early-bird rentals"]),
]


def seed(conn, seed_value=7):
    """Fill an empty database with the demo mailbox."""
    rng = random.Random(seed_value)
    now_ms = int(time.time() * 1000)
    rows, cats, n_id = [], [], 0
    for name, email, category, suggestion, gmail_cat, is_list, count, read_share, subjects in SENDERS:
        domain = email.split("@")[1]
        for i in range(count):
            n_id += 1
            age_days = rng.betavariate(1.2, 3.5) * 1400
            unread = rng.random() > read_share
            labels = {gmail_cat} | ({"UNREAD"} if unread else set()) | ({"INBOX"} if rng.random() < .85 else set())
            subject = rng.choice(subjects).replace("{n}", str(rng.randint(1000, 9999)))
            cols = label_columns(labels)
            rows.append((
                f"demo{n_id:06d}", f"t{n_id}", 1, 0, name, email, domain, subject, subject.lower()[:200],
                domain if is_list else None, f"<https://{domain}/unsubscribe>" if is_list else None,
                "List-Unsubscribe=One-Click" if is_list and rng.random() < .6 else None,
                now_ms - int(age_days * 86400000), rng.choice([18_000, 42_000, 95_000, 240_000, 1_800_000]),
                cols["labels"], cols["in_inbox"], cols["unread"], cols["category"], cols["hidden"],
            ))
        cats.append((email, category, suggestion, "Demo data", "demo-model", int(time.time())))
    conn.executemany(
        """INSERT INTO messages(id, thread_id, fetched, seen_gen, from_name, from_email, from_domain, subject, subject_key,
             list_id, list_unsubscribe, list_unsubscribe_post, date, size, labels, in_inbox, unread, category, hidden)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.executemany("INSERT INTO sender_categories VALUES(?, ?, ?, ?, ?, ?)", cats)
    set_meta(conn, "email", DEMO_EMAIL)
    set_meta(conn, "last_sync", int(time.time()))
    # A few weeks of made-up cleanup history for the Activity page.
    day = 86400
    history = [(20, "trash", "Acme Deals", 212, 31_000_000), (16, "unsubscribe", "Graphic Kitchen", 0, 0),
               (12, "archive", "Contoso Bank", 96, 0), (8, "trash", "4 bundles", 388, 54_000_000),
               (5, "block", "Linkly", 140, 0), (2, "read", "The Daily Brief", 75, 0)]
    for days_ago, action, label, messages, size in history:
        conn.execute(
            "INSERT INTO activity(ts, action, view, label, messages, bytes, detail) VALUES(?, ?, 'sender', ?, ?, ?, ?)",
            (int(time.time()) - days_ago * day, action, label, messages, size,
             '{"method": "one-click"}' if action == "unsubscribe" else None),
        )
    total = len(rows)
    for i, days_ago in enumerate(range(21, -1, -3)):
        inbox = int(total * .86) + 900 - i * 128
        conn.execute("INSERT OR REPLACE INTO snapshots VALUES(?, ?, ?, ?, ?)",
                     (int(time.time()) - days_ago * day, total + 900 - i * 128, inbox, int(inbox * .72), 0))
    conn.commit()
    analytics.snapshot(conn)
