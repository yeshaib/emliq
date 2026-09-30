# emliq guide

emliq (email IQ) helps you clean up a crowded Gmail inbox by working with **bundles**: all the
mail from one sender, domain, mailing list, subject, year or size, handled in one click. It runs
on your computer, and nothing is permanently deleted.

## Getting started

### Try the demo first

Run `emliq demo` to open a made-up mailbox. Everything in it is fictional and nothing can change
Gmail, so it's a safe place to learn how emliq works.

### Connect your Gmail

emliq talks to Gmail through a free sign-in "client" that you create once in your own Google
Cloud account. It takes about 5 minutes.

1. Open [Google Cloud Console](https://console.cloud.google.com/projectcreate) and create a project (any name, for example `emliq`). No billing is needed.
2. Turn on the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) for that project.
3. Open **Google Auth Platform**, click **Get started**, enter an app name and your email, choose **External**, and finish.
4. Under **Audience → Test users**, add your own Gmail address.
5. Under **Clients**, create a client of type **Desktop app** and click **Download JSON**.
6. In emliq, open **Settings → Gmail account**, choose the downloaded file, then click **Sign in with Google**.

On Google's screen, click **Continue** past "Google hasn't verified this app" (it's your own app)
and **tick every checkbox**. If a box is left unticked, emliq tells you which permission is missing.

> While your Google app is in "Testing" mode, Google asks you to sign in again every 7 days. emliq shows a banner when it's time.

### Load your mail

Click **Load all unread** in the header. emliq downloads the details of every unread message
(sender, subject, date, size), not the messages themselves. After that, **Sync** keeps emliq up to
date with anything that changed in Gmail.

## The screen

- **Left menu:** how mail is grouped (Senders, Domains, Mailing lists and so on), plus Ask AI, Activity, Settings and Help.
- **Header:** the scope (**Inbox**, **Unread** or **All mail**), **Load all unread**, **Insights**, **Settings** and **Sync**.
- **Search bar:** type and press Enter to search, or click **Ask AI** to ask a question.
- **Bundle list:** the main table. Each row is one bundle.
- **Insights panel:** summary numbers and charts on the right.
- **Version badge:** bottom-right corner. Click it to see what's new.

## Scopes: Inbox, Unread, All mail

The scope decides which messages are counted and acted on.

- **Unread** (the default) covers unread messages anywhere in your mailbox.
- **Inbox** covers messages currently in your inbox, read or not.
- **All mail** covers everything emliq has loaded.

Actions apply only to messages in the current scope. For example, archiving a sender while on
**Unread** archives only that sender's unread messages.

## Grouping mail into bundles

Pick a grouping in the left menu:

| Grouping | Each bundle is |
|---|---|
| Senders | One sender address |
| Domains | Everyone sending from one domain, like all of a store's addresses |
| Mailing lists | One newsletter or mailing list |
| Subjects | Messages with the same subject, ignoring numbers (so "Order #123" and "Order #456" match) |
| Gmail categories | Gmail's Primary, Promotions, Social, Updates and Forums tabs |
| AI categories | Categories assigned by AI (see AI categories below) |
| By year | Messages received in each year |
| By size | Messages grouped by how much space they take |

Each row shows the number of messages, how many are unread, the space they use and the latest
date. Click the **⌄** arrow on a row to see its messages, and click a message to open it in Gmail.

Use the filter box to find bundles by name, subject or address, and the sort menu to order them
by most messages, largest, most unread or most recent. Long lists are split into pages; choose
15, 30 or 50 rows per page at the bottom.

## Selecting several bundles

- Tick a row's **checkbox**, or click its round **avatar circle**.
- Once something is selected, click anywhere on another row to add it.
- **Shift-click** selects everything between the last row you clicked and this one.
- The checkbox at the top of the list selects the whole page.

Selections stay when you change pages. A bar at the bottom shows how many bundles and messages
you've picked, with **Mark read**, **Archive**, **Unsubscribe**, **Block** and **Trash**.

## What each action does

Every action asks you to confirm first.

| Action | What happens |
|---|---|
| Mark read | Marks the bundle's messages as read |
| Archive | Removes them from your inbox; they stay searchable in Gmail's All Mail |
| Trash | Moves them to Gmail's Trash, where you can recover them for 30 days |
| Unsubscribe | Unsubscribes you from the sender's mailing list (see below) |
| Block | Creates a Gmail filter so future mail from the sender skips your inbox |

emliq never permanently deletes mail. Gmail empties its Trash by itself after 30 days.

### Unsubscribe

emliq tries, in order:

1. **One-click unsubscribe:** the sender's official instant unsubscribe, if they support it.
2. **Unsubscribe email:** emliq sends the sender's unsubscribe request from your Gmail account.
3. **Unsubscribe page:** if the sender only offers a web page, emliq gives you a button to open it.

Afterwards emliq offers to move that sender's existing messages to Trash. When you unsubscribe
from several senders at once, a results window shows what happened for each one.

> Unsubscribing asks the sender to stop. Most comply within a few days; for any that don't, use Block.

### Block

Block creates a real Gmail filter, so future messages from that sender (or domain, list or
subject) are archived and marked read automatically, even when emliq isn't running. It also
archives the messages already there. To undo it, delete the filter in Gmail under
**Settings → Filters and blocked addresses**.

## AI categories

AI can sort your senders into categories like Newsletters, Shopping & deals, Finance & banking or
Personal, and suggest whether to **keep**, **archive** or **unsubscribe** from each.

1. Choose a provider in **Settings → AI provider** (see Choosing an AI provider below).
2. Click **Categorize senders** on the AI categories tile in the Insights panel.
3. emliq shows the estimated cost or time and asks before it starts.

A progress panel appears in the bottom-right corner, with a **Stop** button. Everything finished
so far is kept, and **Categorize remaining senders** picks up where you left off.

When it's done:

- Sender rows show their category and a suggestion such as **Unsubscribe?**. Hover over the suggestion to see why.
- The **AI categories** grouping lists each category; expand one to see its senders first, then click a sender for its emails.
- The **Any suggestion** and **Any category** filters narrow the list. For example, choose **Suggested: unsubscribe**, select the page, and unsubscribe in bulk.

Suggestions are only suggestions. Nothing happens to your mail until you choose an action.

### Choosing an AI provider

| | Local model (Ollama) | Claude (Anthropic API) |
|---|---|---|
| Cost | Free | About $2–5 once for ~2,000 senders; a few cents per question |
| Privacy | Nothing leaves your computer | Sender names, addresses, counts and a few subject lines go to Anthropic |
| Speed | About 30 minutes for ~2,000 senders on an Apple Silicon Mac | A few minutes |
| Setup | Install [Ollama](https://ollama.com), then download a model in Settings | Paste an API key in Settings |

For Ollama, **qwen3:14b** (9.3 GB) is the most accurate choice for a Mac with 24 GB of memory or
more; **qwen3:8b** (5.2 GB) is about twice as fast and fine with 16 GB.

With either provider, AI never sees the content of your emails, because emliq never downloads it.

## Ask AI

Ask questions about your mailbox in plain language. Type in the search bar and click **Ask AI**,
or open **Ask AI** in the left menu. For example:

- Which mailing lists do I never read?
- What's taking up the most space?
- Who sent me the most email this month?
- Which senders haven't emailed me in 6 months?
- Anything from a real person I haven't read this week?

The AI looks things up in emliq's copy of your mail and answers with numbers and sender names.
When it finds senders, it adds a button such as **Open these 12 senders**. That opens them in the
list already selected, so you can review and act on them. The AI itself can't change your mail.

Tips:

- Be specific: "newsletters I never read" works better than "junk".
- Follow-up questions work: "only the ones from this year".
- A local model sometimes misses details; switch to Claude, or try qwen3:14b, for harder questions.

## Search

Type in the search bar and press Enter. Results show matching **senders** (with their AI
suggestions) and matching **messages** (by subject or sender), newest first. Click a sender to
open it in the list, or **Ask AI about this** to ask a question about the results.

Search covers what emliq has loaded. To include older read mail, see Loading more mail below.

## Insights panel

The panel on the right shows summary numbers, your top senders, mail by year, AI categories and
Gmail categories. Click a bar to open that bundle.

- Click **»** or the **Insights** button to collapse it to a slim bar; click **«** or a tile icon to bring it back.
- On smaller windows it opens as a drawer over the page.
- Hover over a tile and click its **✕** to hide it. **Customize** lets you hide or restore tiles and left-menu groupings.

## Activity

**Activity** in the left menu records everything emliq has done: trash, archive, mark read,
unsubscribe (and how), block, syncs, AI runs and sign-ins. It shows totals such as messages
cleaned and storage freed, your inbox size over time and messages cleaned per day. The log is
stored only on your computer.

## Settings

- **Gmail account:** who's signed in, **Sign out** and **Switch account**.
- **AI provider:** Claude or a local model, the Ollama model and downloads, and your Anthropic key.
- **Dashboard and menu:** show or hide tiles and groupings.
- **About this install:** your data folder and exactly what emliq stores.

### Signing out

Signing out removes emliq's access to your Google account and never changes Gmail. By default
emliq keeps its local copy, so signing back in is quick. Tick **Also delete emliq's cached mail
data** to remove it. Signing in with a *different* Google account clears the previous account's
data automatically, so two mailboxes never mix.

## Loading more mail

- **Sync** fetches everything that changed since the last sync.
- **Load all unread** fetches every unread message, however old.
- To load everything else too, including old read mail, run `emliq sync --full` in a terminal. Large mailboxes take a while, because Gmail limits how fast apps can read.

A progress panel in the bottom-right corner shows each step, for example
"Step 2 of 3 · 6,000 of ~12,434". If a sync is interrupted, the next one picks up where it stopped.

## Privacy and your data

- emliq stores only each message's sender, subject, date, Gmail labels, size and unsubscribe link. Never the content or attachments.
- Everything is kept in one folder on your computer: `~/.emliq` on macOS and Linux, `C:\Users\you\.emliq` on Windows.
- The app only accepts connections from your own computer.
- Nothing is sent anywhere except to Gmail, and to Anthropic only if you choose Claude.

To remove everything: sign out with **Also delete emliq's cached mail data** ticked, remove your
Anthropic key in Settings, then delete the data folder. You can also revoke access at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Troubleshooting

**"You're not signed in" or "Your Google sign-in expired."**
Click **Sign in with Google** in the banner or in Settings. In Google's Testing mode this happens every 7 days.

**"Not all permissions were granted."**
Sign in again and tick every checkbox on Google's permission screen.

**Sync is slow or says "Gmail rate limit".**
Gmail limits how quickly apps can read mail. emliq pauses and continues on its own, and keeps everything it has already loaded.

**"Can't reach Ollama."**
Open the Ollama app (or run `ollama serve`) and check that a model is downloaded in Settings.

**An unsubscribe didn't work.**
Some senders ignore unsubscribe requests or take a few days. Use **Block** to keep their mail out of your inbox.

**Numbers in emliq don't match Gmail.**
emliq counts what it has loaded. Use **Load all unread**, or `emliq sync --full` for everything, then **Sync**.

**The page doesn't respond.**
emliq runs on your computer. Make sure `emliq serve` (or the Docker container) is still running, then reload the page.

## Keyboard tips

- **?** opens this guide.
- **Enter** in the search bar searches; **Enter** in Ask AI sends your question, **Shift+Enter** adds a new line.
- **Esc** closes any popup without doing anything.
- **Shift-click** selects a range of rows.
