"""English UI copy - a key-for-key translation of `app/ui/i18n.py`'s Czech
`STRINGS` (the parity is enforced by `tests/ui/test_i18n.py`). Selected per
browser via the header's language toggle - see `i18n.current_language`.

Prices stay in the local currency (CZK) in both languages: the catalog
only covers the Czech market.
"""

STRINGS_EN: dict = {
    "header": {
        "brand": "Rovis",
        "tagline": "Describe your lifestyle. We'll find you a car.",
        "restart": "Start over",
        "technicalRequirements": "Technical requirements",
        "startWizard": "Selection guide",
        "apiKey": "AI key",
        "apiKeyMissing": "AI key missing",
        "login": "Log in",
        "logout": "Log out",
        "account": "Account",
        "admin": "Admin",
        "articles": "Articles",
        "myArticles": "My articles",
        "becomeAuthor": "Become an author",
        "sendFeedback": "Send feedback",
        "switchLanguage": "Čeština",
    },
    "common": {
        "dateFormat": "%d/%m/%Y",
    },
    "admin": {
        "title": "Rovis — Admin",
        "sources": "Sources (config/sources.yaml)",
        "active": "active",
        "inactive": "inactive",
        "run": "Run",
        "running": "Running…",
        "done": "Done",
        "failed": "Failed (exit code {code})",
        "progress": {
            "starting": "Starting…",
            "step": "{step} / {steps} · {item}",
            "sub": "({sub} / {subs})",
            "elapsed": "Running {elapsed}",
            "remaining": "about {remaining} left",
            "lastRun": "Last successful run took {duration}",
        },
        "jobs": {
            "scraper": {
                "title": "1. Run the scraper",
                "description": (
                    "Downloads and parses new price lists from all active sources into storage/scraper.db. "
                    "On its own it doesn't change the catalog the app shows - that's what the next step is for."
                ),
            },
            "import": {
                "title": "2. Import into the catalog",
                "description": (
                    "Copies newly parsed data from storage/scraper.db into the catalog (storage/drivewise.db) "
                    "- only after this step do new/updated cars show up in the app. Safe to run "
                    "repeatedly."
                ),
            },
        },
        "tabs": {
            "data": "Data",
            "controls": "Controls",
            "aiTrace": "AI communication",
            "authors": "Authors",
            "feedback": "Feedback",
            "feedbackNew": "Feedback ({count})",
            "comparisons": "Comparisons",
        },
        "trace": {
            "title": "Communication with the AI ({provider})",
            "description": (
                "A complete record of every AI API call — the exact request sent, the full response "
                "or error, tokens and duration. Kept only in server memory (the last {max} calls), "
                "gone after a restart. Contains text users typed into the chat."
            ),
            "disabled": "Tracing is turned off (LLM_TRACE_MAX_ENTRIES=0).",
            "summary": "{count} calls · {errors} errors · {tokens} tokens",
            "autoRefresh": "Live refresh",
            "refresh": "Refresh",
            "clear": "Clear",
            "empty": "No calls yet. Type something into the app's chat and the record will show up here.",
            "ok": "OK",
            "failed": "Error: {code}",
            "tokens": "{input} → {output} tokens",
            "noUsage": "tokens not reported",
            "request": "Request",
            "reply": "Reply (text)",
            "error": "Error",
            "rawRequest": "Raw request (JSON)",
            "rawResponse": "Raw response (JSON)",
            "emptyReply": "(empty reply)",
            "purposes": {
                "requirement_extraction": "Requirement extraction",
                "explanation": "Recommendation explanation",
                "unknown": "Unspecified",
            },
        },
    },
    "authors": {
        "request": {
            "title": "Become an author",
            "description": (
                "Authors can write and publish articles on the Rovis portal - to everyone or to "
                "selected users only. An administrator reviews the request."
            ),
            "nameLabel": "Name to publish under",
            "messageLabel": "Message for the administrator (optional)",
            "submit": "Send request",
            "sending": "Sending…",
            "close": "Close",
            "pending": "Your request from {date} is waiting for an administrator's approval.",
            "sent": 'Request sent. Once an administrator approves it, you\'ll find "My articles" in the account menu.',
            "rejected": "Your previous request from {date} was rejected. You can send a new one.",
        },
        "admin": {
            "pendingTitle": "Author role requests",
            "noPending": "No pending requests.",
            "requested": "Requested {date}",
            "approve": "Approve",
            "reject": "Reject",
            "authorsTitle": "Authors",
            "noAuthors": "No authors yet.",
            "articleCount": "Articles: {count}",
            "revoke": "Revoke role",
            "approved": "Author role granted: {email}",
            "rejectedNote": "Request rejected: {email}",
            "revoked": "Author role revoked: {email}",
        },
        "errors": {
            "invalid_name": "Please fill in a name (at most 120 characters).",
            "message_too_long": "The message is too long (at most 2000 characters).",
            "already_author": "You already are an author.",
            "already_pending": "Your request is already waiting for approval.",
            "forbidden": "You aren't allowed to do this.",
            "not_found": "The request or user wasn't found.",
            "already_decided": "The request has already been decided.",
            "unknown_error": "Something went wrong. Please try again.",
        },
    },
    "comparisonStats": {
        "description": (
            "The most compared models and the models users most often compare them with. "
            "Every displayed comparison of 2 or more cars counts (anonymously, not tied to a user)."
        ),
        "periods": {"7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days", "all": "All time"},
        "total": {"one": "{count} comparison in the period", "other": "{count} comparisons in the period"},
        "comparisons": {"one": "compared {count}×", "other": "compared {count}×"},
        "withinModel": {
            "one": "of which {count}× comparing its own trims/engines",
            "other": "of which {count}× comparing its own trims/engines",
        },
        "partners": "Most often compared with",
        "partnerCount": "{count}× · {share} %",
        "empty": "Nobody has compared 2 or more cars in this period yet.",
        "errors": {
            "forbidden": "You don't have permission to see the statistics.",
            "unknown_error": "The statistics couldn't be loaded.",
        },
    },
    "feedback": {
        "dialog": {
            "title": "Send feedback",
            "description": (
                "Found a bug, have an idea for an improvement, or did something make you happy? "
                "Let us know - an administrator will read it."
            ),
            "textLabel": "Your message",
            "textPlaceholder": "What happened, what you'd like, or what you liked…",
            "attachRequirements": "Attach my current car requirements",
            "contextNote": "Sent along with your message: app version ({version}), language and app section ({page}).",
            "submit": "Send",
            "sending": "Sending…",
            "close": "Close",
            "sent": "Thank you! We've got your message.",
        },
        "types": {"bug": "Bug", "idea": "Idea", "praise": "Praise", "other": "Other"},
        "statuses": {
            "new": "New",
            "in_progress": "In progress",
            "resolved": "Resolved",
            "wont_fix": "Won't fix",
            "duplicate": "Duplicate",
        },
        "pages": {"search": "car search"},
        "admin": {
            "empty": "No feedback.",
            "allTypes": "All types",
            "allStatuses": "All statuses",
            "context": "Sent from: {page} · version {version} · language {language}",
            "requirements": "Attached requirements",
            "note": "Internal note",
            "save": "Save",
            "saved": "Saved.",
        },
        "errors": {
            "empty_text": "Please write a message.",
            "text_too_long": "The message is too long (4000 characters at most).",
            "note_too_long": "The note is too long (4000 characters at most).",
            "invalid_type": "Please pick what it's about (bug, idea, praise, other).",
            "invalid_status": "Invalid status.",
            "rate_limited": "You've sent a lot of messages today. Please try again tomorrow.",
            "forbidden": "You don't have permission for this action.",
            "not_found": "Feedback not found.",
            "unknown_error": "Something went wrong. Please try again.",
        },
    },
    "articles": {
        "pageTitle": "Articles — Rovis",
        "title": "Articles",
        "empty": "There are no articles yet.",
        "byline": "{author} · {date}",
        "editorial": "Rovis editorial team",
        "sharedWithYou": "Shared with you",
        "notFound": "The article doesn't exist, or you don't have access to it.",
        "notFoundHint": "If someone shared it with you, log in with the email they sent it to.",
        "backToList": "← All articles",
        "backToApp": "← Back to choosing a car",
        "edit": "Edit",
        "languages": {"cs": "Czech", "en": "English"},
        "onlyIn": {
            "cs": "This article is only available in Czech so far.",
            "en": "This article is only available in English so far.",
        },
        "onlyInBadge": {"cs": "Czech only", "en": "English only"},
        "readIn": {"cs": "Číst česky", "en": "Read in English"},
        "visibility": {
            "label": "Who can see the article",
            "draft": "Only me (draft)",
            "restricted": "Selected users",
            "public": "Everyone",
        },
        "author": {
            "pageTitle": "My articles — Rovis",
            "title": "My articles",
            "new": "New article",
            "empty": "You haven't written any articles yet.",
            "updated": "Edited {date}",
            "onlyAuthors": "This page is for authors only.",
            "onlyAuthorsHint": 'You can ask for the author role in the account menu on the main page ("Become an author").',
            "backToMine": "← My articles",
        },
        "editor": {
            "newTitle": "New article",
            "editTitle": "Edit article",
            "titleLabel": "Title",
            "placeholder": "Start writing…",
            "languagesHint": (
                "You can write the article in Czech, English, or both. One tab is enough - readers of the "
                "other language get the available version with a notice."
            ),
            "emptyVersion": "empty",
            "recipientsLabel": "Readers' emails (separate with commas or new lines)",
            "recipientsHint": "They'll see the article after logging in with that email - even if they don't have an account yet.",
            "saveDraft": "Save draft",
            "publish": "Publish",
            "saving": "Saving…",
            "saved": "Saved",
            "published": "Published",
            "view": "View",
            "delete": "Delete",
            "confirmDelete": 'Really delete the article "{title}"? This can\'t be undone.',
            "cancel": "Cancel",
            "deleted": "Article deleted",
        },
        "errors": {
            "forbidden": "You aren't allowed to do this.",
            "not_found": "The article doesn't exist.",
            "empty_title": "Please fill in the title and text of at least one language version.",
            "missing_title": "Please add a title (version: {detail}).",
            "title_too_long": "The title is too long (at most 200 characters).",
            "content_too_long": "The article is too long - try shrinking or removing embedded images.",
            "invalid_recipient": "Invalid email address: {detail}",
            "no_recipients": "Enter at least one reader's email, or pick a different visibility.",
            "too_many_recipients": "Too many readers (at most 200).",
            "unknown_error": "Something went wrong. Please try again.",
        },
    },
    "mobileTabs": {
        "chat": "Conversation",
        "results": "Results",
    },
    "auth": {
        "title": "Log in",
        "emailDescription": (
            "Enter your email — we'll send you a one-time code. An account is created automatically, "
            "no password needed."
        ),
        "emailLabel": "Email",
        "sendCode": "Send code",
        "sending": "Sending…",
        "codeDescription": "We sent a six-digit code to {email}. It is valid for {minutes} minutes.",
        "codeLabel": "Code from the email",
        "verify": "Confirm",
        "verifying": "Verifying…",
        "consoleNotice": (
            "Development mode: no email is sent, the code is printed in the server log. "
            "For real emails set EMAIL_BACKEND=smtp and SMTP_* (see the README)."
        ),
        "resend": "Send a new code",
        "changeEmail": "Change email",
        "cancel": "Cancel",
        "adminOnly": "This page is for administrators only.",
        "adminOnlyLoggedIn": "You are logged in as {email}, but this account doesn't have administrator rights.",
        "backToApp": "← Back to the app",
        "errors": {
            "invalid_email": "Please enter a valid email address.",
            "rate_limited": "Too many code requests. Please try again in a moment.",
            "email_delivery_failed": "The email couldn't be sent. Please try again in a moment.",
            "email_not_configured": "Sending emails isn't set up (EMAIL_BACKEND / SMTP_* on the server).",
            "invalid_code": "The code is wrong or has expired.",
            "too_many_attempts": "Too many wrong attempts. Please request a new code.",
            "account_disabled": "This account is blocked.",
            "unknown_error": "Something went wrong. Please try again.",
        },
    },
    "apiKey": {
        "title": "API key for the AI ({provider})",
        "description": (
            "The key is kept only in the running application's memory — never on disk or in the source code. "
            "After the application restarts it has to be entered again."
        ),
        "label": "API key",
        "getKey": "You can get a key for free at {url}.",
        "configured": "The AI key is set.",
        "save": "Save",
        "cancel": "Cancel",
        "clear": "Remove key",
        "empty": "Please enter a key.",
        "invalid": (
            "The key contains a disallowed character “{char}” at position {position}. A real key "
            "consists only of letters, digits and underscores, without spaces — try pasting it again (Ctrl+V)."
        ),
    },
    "chat": {
        "typePlaceholder": "Type your answer…",
        "send": "Send",
        "sending": "Thinking…",
        "aiNotConfigured": (
            "The AI layer isn't set up yet (missing API key) — the conversation works, "
            "but without understanding requirements or making recommendations."
        ),
        "genericError": "Something went wrong. Please try again.",
        "restoreSummary": "My saved requirements from the last session.",
        "errors": {
            "ai_invalid_key": (
                "The AI service rejected the API key (invalid or revoked). "
                "Enter it again via “AI key” in the account menu at the top right."
            ),
            "ai_invalid_key_user": (
                "The AI service is temporarily unavailable (invalid API key on the server side). "
                "Please let the administrator know."
            ),
            "ai_rate_limited": "The AI service's request limit was exceeded. Please try again in a moment.",
            "ai_model_unavailable": (
                "The selected AI model isn't available. Check the model setting (GROQ_MODEL / CLAUDE_MODEL)."
            ),
            "ai_unreachable": "Couldn't connect to the AI service. Check your internet connection.",
            "ai_error": "The AI service returned an error. Please try again.",
            # ConversationLimitError codes (app/services/conversation.py).
            "message_too_long": "Your message is too long. Please shorten it.",
            "rate_limited": "You've sent too many messages in a short time. Please try again later.",
            "conversation_too_long": "This conversation is too long. Please start a new one.",
            "conversation_expired": "This conversation has expired. Please reload the page.",
        },
    },
    "wizard": {
        "title": "Car selection guide",
        "subtitle": "Ten short questions — at the end we'll show you right away what in the catalog fits.",
        "progress": "Question {step} of {total}",
        "back": "Back",
        "next": "Next",
        "skip": "Not sure / skip",
        "finish": "Show recommendations",
        "close": "Close",
        "summaryIntro": "I filled in the guide",
        "notes": {
            "brandPref": "Brand preference: {value}",
            "annualKm": "Annual mileage approx. {km} km",
        },
        "questions": {
            "budget": {
                "title": "What is your budget for a new car?",
                "placeholder": "E.g. 800000",
                "unit": "CZK",
                "summary": "budget up to {amount} CZK",
            },
            "usage": {
                "title": "What will you use the car for most?",
                "options": {
                    "commute": "Commuting to work",
                    "family": "Family trips",
                    "cargo": "Carrying cargo",
                    "mixed": "A mix of everything",
                },
            },
            "seats": {
                "title": "How many people will the car regularly carry?",
                "placeholder": "E.g. 5",
                "summary": "at least {count} seats",
            },
            "bodyType": {
                "title": "What should the car look like and how big should it be?",
                "hint": (
                    "A smaller city car, a practical estate for frequent trips, a taller SUV with a better "
                    "view, or a large family car for 7 people."
                ),
                "options": {
                    "Hatchback": "Smaller city car",
                    "Kombi": "Practical estate",
                    "SUV": "Taller SUV",
                    "MPV": "Large family car (7 seats)",
                },
            },
            "awd": {
                "title": "Do you also drive where there's mud, snow or rough roads (cottage, mountains, fields)?",
                "hint": "If so, a car with all-wheel drive is a good fit – it grips better on slippery surfaces.",
                "yes": "Yes, often",
                "no": "No, I mostly drive on roads",
            },
            "fuel": {
                "title": "What does your typical driving look like?",
                "options": {
                    "electric": "Mostly short trips around town, I can charge at home or at work",
                    "hybrid": "A mix of town driving and frequent longer trips",
                    "diesel": "I drive a lot and over long distances (motorways, business trips)",
                    "petrol": "I drive little or irregularly and want to keep it simple",
                },
            },
            "mileage": {
                "title": "Roughly how many kilometres do you drive per year?",
                "placeholder": "E.g. 15000",
                "summary": "annual mileage approx. {km} km",
            },
            "cargo": {
                "title": "Do you often carry something bulky?",
                "options": {
                    "stroller": "A pram",
                    "sports": "Sports equipment",
                    "tools": "Tools",
                    "trailer": "I tow a trailer or a boat",
                    "none": "None of these",
                },
            },
            "brand": {
                "title": "Do you prefer a particular brand, or want to rule one out?",
                "placeholder": "E.g. I prefer Škoda, no Fiat",
            },
            "priority": {
                "title": "What would annoy you most about a badly chosen car?",
                "options": {
                    "cost": "High running costs",
                    "repairs": "Frequent repairs",
                    "power": "Lack of power",
                    "comfort": "Discomfort on long trips",
                },
            },
        },
    },
    "results": {
        "title": {
            "one": "{count} match for you",
            "other": "{count} matches for you",
        },
        "browsingTitle": {
            "one": "{count} car in the catalog",
            "other": "{count} cars in the catalog",
        },
        "updated": "Updated based on your last message",
        "startPrompt": "Start a conversation and the AI will narrow the catalog down to your needs.",
        "emptyState": "Nothing matches your requirements yet — try adjusting them in the conversation.",
        "loadingMore": "Loading more…",
        "loadingCatalog": "Loading the catalog…",
        "loadingTitle": "Car catalog",
        "catalogError": "Couldn't load the car catalog.",
        "sortBy": "Sort by",
        "sort": {
            "recommended": "Recommended",
            "price_asc": "Price: low to high",
            "price_desc": "Price: high to low",
            "alpha": "Alphabetical",
            "custom": "My order",
        },
        "dragHint": "Drag to reorder",
        "dragHintTouch": "Reorder by dragging a card by its ⠿ handle.",
        "controlsToggle": "Sort & filters",
        "filters": {
            "all": "All",
            "brand": "Manufacturer",
            "fuelType": "Engine type",
            "drivetrain": "Drive",
        },
    },
    "car": {
        "photoPlaceholder": "car photo — {make} {model}",
        "topMatch": "Top match",
        "like": "I like it — favourite models get priority in search",
    },
    "compare": {
        "toggle": "Compare",
        "full": "You can compare at most {max} cars. Remove one first.",
        "trayTitle": "To compare",
        "trayCount": "To compare: {count}",
        "open": "Compare ({count})",
        "needTwo": "Pick at least 2 cars.",
        "clear": "Clear",
        "remove": "Remove from comparison",
        "title": "Car comparison",
        "differencesOnly": "Show differences only",
        "bestHint": "Highlighted = best value in the row",
        "loading": "Loading the comparison…",
        "error": "Couldn't load the comparison.",
        "tooFew": "Only one car is left to compare — add more from the results.",
        "noDifferences": "The cars don't differ in this section.",
        "detail": "Detail",
        "standard": "✓ included",
        "missing": "—",
        "colorSummary": "Colours: {count} · {range}",
        "perBrandNote": (
            "Every brand names its equipment differently, so for cars of different brands it's listed per car."
        ),
        "standardCount": "Standard equipment ({count})",
        "optionalCount": "Optional equipment ({count})",
        "add": "Add to comparison",
        "added": "In comparison",
        "compareTrims": "Compare trims",
        "sections": {
            "overview": "Overview",
            "equipment": "Equipment",
        },
        "rows": {
            "price": "Price",
            "matchScore": "Match",
            "colors": "Colour range",
        },
        "trimPicker": {
            "title": "Which trims to compare?",
            "hint": "Pick 2 to {max}. Your trim and the closest in price are preselected.",
            "sameEngine": "same engine",
            "otherEngine": "different engine (cheapest variant)",
            "current": "yours",
            "selected": "{count} of {max} selected",
            "confirm": "Compare",
            "cancel": "Cancel",
            "single": "This model comes in only one trim in the catalog.",
            "loading": "Loading trims…",
        },
        "pdf": {
            "title": "Car comparison",
        },
    },
    "requirements": {
        "subtitle": "Plain language, translated into technical specifications.",
        "empty": "No requirements captured yet.",
        "close": "Close",
    },
    "share": {
        "button": "Share",
        "creating": "Preparing the link…",
        "error": "The link couldn't be created. Please try again.",
        "title": "Share selection",
        "description": (
            "Anyone with this link will see this selection, even without an account. The link is valid "
            "until {date} and doesn't contain your name or email."
        ),
        "copy": "Copy link",
        "copied": "Link copied",
        "native": "Share…",
        "nativeTitle": "Car selection from Rovis",
        "qrHint": "Scan it with your phone, e.g. at the dealership.",
        "close": "Close",
        "pageTitle": "Shared car selection · Rovis",
        "heading": {
            "one": "Shared selection: {count} car",
            "other": "Shared selection: {count} cars",
        },
        "asOf": "Prices as of {created} · link valid until {expires}",
        "requirements": "Requirements",
        "priceNote": (
            "Prices come from manufacturers' price lists as of the sharing date and may have changed since. "
            "You'll find the current offer in the app or at a dealer."
        ),
        "findOwn": "Find your own car",
        "notFound": "The link doesn't exist or has already expired.",
        "notFoundHint": "Shared links are valid for a limited time. Ask for a new one, or find a car yourself.",
    },
    "vehicleDetail": {
        "close": "Close",
        "exportPdf": "Download PDF",
        "exportPdfError": "The PDF couldn't be created.",
        "loading": "Loading car details…",
        "error": "Couldn't load the car details.",
        "sections": {
            "powertrain": "Engine & drivetrain",
            "colors": "Colours",
            "standardEquipment": "Standard equipment",
            "optionalEquipment": "Optional equipment",
            "priceHistory": "Price history",
        },
        "fields": {
            "fuelType": "Fuel",
            "transmission": "Transmission",
            "drivetrain": "Drive",
            "power": "Power",
            "consumption": "Consumption",
            "co2": "CO₂ emissions",
            "noData": "Not available",
        },
        "units": {
            "hp": "hp",
        },
        "priceHistory": {
            "current": "current",
            "lowestPrice30d": "lowest price in 30 days: {price}",
        },
        "pdf": {
            "created": "Created {date}",
            "included": "included",
            "page": "Page {page}/{total}",
            "disclaimer": (
                "Data comes from manufacturers' price lists and may change. A dealer will give you a binding offer."
            ),
        },
        "noColors": "No colour options available.",
        "noOptionalEquipment": "No optional equipment available.",
        "enums": {
            "fuelType": {
                "petrol": "Petrol",
                "diesel": "Diesel",
                "hybrid": "Hybrid",
                "mild_hybrid": "Mild hybrid",
                "phev": "Plug-in hybrid",
                "electric": "Electric",
            },
            "drivetrain": {
                "fwd": "Front-wheel drive",
                "rwd": "Rear-wheel drive",
                "awd": "All-wheel drive (4×4)",
            },
            "consumptionUnit": {
                "l_100km": "l/100 km",
                "kwh_100km": "kWh/100 km",
            },
            "colorFinish": {
                "solid": "Solid",
                "metallic": "Metallic",
                "pearlescent": "Pearlescent",
            },
            "optionCategory": {
                "equipment": "Equipment",
                "package": "Package",
                "warranty": "Warranty",
                "service": "Service",
            },
        },
    },
}
