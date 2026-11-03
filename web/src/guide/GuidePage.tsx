import { Mermaid } from "@ant-design/x";
import { Typography } from "antd";
import { Link } from "react-router-dom";

import { FRESHNESS, ONE_TURN, REQUEST_PATH, SEARCH_VECTORS, VECTOR_WRITE } from "./diagrams";

const CHOICES = [
  {
    title: "LangChain and typed tools",
    body: "The model cannot read the product table by itself. On a search turn the first call is search_products. After that it may search again or call list_categories, which returns category names. Clarify may search once, and then the tools are taken away. Off-catalog and chat get no tools. A product name in the written reply is a prompt rule. When the thread is read back, a card whose id is missing from the tool result is left out.",
  },
  {
    title: "The graph is compiled once",
    body: "When the API starts, it builds the agent once and keeps that object. The chat model is chosen then, from FAKE_LLM, so switching between the scripted model and gpt-6-luna means restarting the process. The route check and the product review read FAKE_LLM again on each turn. With the live model, a thread past 6000 tokens is summarized and the last 12 messages are kept.",
  },
  {
    title: "Celery, and a scheduler for local dev",
    body: "A worker copies the remote catalog into Postgres on a timer. Chat never calls that remote source. The API also copies on startup, and runs that copy on its own timer, when AUTO_SYNC is on and SYNC_MODE=inprocess. Celery beat uses SYNC_INTERVAL_MINUTES and does not read AUTO_SYNC. It also copies the remote category list every day at 03:00. Redis is the queue and the lock for that copy.",
  },
  {
    title: "Embeddings stay on this machine",
    body: "A local model turns each product text into 384 numbers and stores that list on the row. Both embedders write the same column, and that column has the HNSW index. The search diagram is the lookup. The second catalog diagram is the write. gpt-6-luna never sees those lists. Hash mode stores the list and does not take the neighbor step. Full text uses a GIN index.",
  },
  {
    title: "Decisions routes, then reviews the cards",
    body: "Before any search, the Decisions API reads the last six messages and chooses search, clarify, off-catalog, or chat. It does not choose keywords or a price. If it says search and the chance of a named product or place is under 0.5, the server treats the turn as clarify. With the live model, Decisions scores each returned product and drops one under 0.5 before the cards are sent. With FAKE_LLM=1 a phrase table picks the route and that score is skipped.",
  },
  {
    title: "Ant Design X",
    body: "The sidebar, the empty state, the bubbles, the cards, and the stop button are one chat kit. The sidebar shows each question once, as the newest chat. Asking that question again from the empty home page opens the existing chat and does not send the message. Inside a chat, the same text is a new turn. Delete removes every chat with that title.",
  },
  {
    title: "The live turn is SSE",
    body: "The browser posts the message and reads a stream. The events are a status, then each group of cards, then each answer token, then done. An error is its own event. Closing the tab does not cancel the turn. The next load shows the finished answer. Stop cancels the turn and keeps whatever was already saved.",
  },
];

export function GuidePage() {
  return (
    <main className="guide">
      <header className="guide-header">
        <Link to="/">Back to chat</Link>
        <Typography.Title level={2}>How this shop works</Typography.Title>
      </header>
      <Typography.Paragraph>
        You ask for something in chat. The server decides what kind of request that is, searches a local product table when the request is about shopping, and streams an answer with product cards. The chat does not call the remote catalog. A worker has already copied that catalog into Postgres.
      </Typography.Paragraph>

      <section data-testid="diagram-turn">
        <Typography.Title level={4}>One message</Typography.Title>
        <Typography.Paragraph>
          Read this from top to bottom. Step 2 reads the last six messages and picks the route. A search that names no product and no place, or a route outside the four names, becomes clarify. Step 4 runs for the live model. The scripted model keeps the search result. A flight or a thank-you skips the catalog and goes straight to a short reply.
        </Typography.Paragraph>
        <Mermaid>{ONE_TURN}</Mermaid>
      </section>

      <section>
        <Typography.Title level={4}>The four routes</Typography.Title>
        <Typography.Paragraph>
          Search is a named product or a place. “A phone under 500” searches phones and keeps the ones at or below 500. “Something for the living room” is a search. The live model is asked to search home decoration and to name a top pick from the cards. The scripted model sends the whole sentence as the query and does not set that category.
        </Typography.Paragraph>
        <Typography.Paragraph>
          Clarify is a wish with no product and no place, such as “something cheap and cool.” The server still searches, then asks one question using the real categories and prices. It does not invent a mixed assortment.
        </Typography.Paragraph>
        <Typography.Paragraph>
          Off catalog is something this store does not sell, such as “a flight to Tokyo.” There is no search and there are no cards. The reply says what the store does sell.
        </Typography.Paragraph>
        <Typography.Paragraph>
          Chat is hello or thanks. There is no search and no product names.
        </Typography.Paragraph>
      </section>

      <section data-testid="diagram-request">
        <Typography.Title level={4}>Who talks to whom</Typography.Title>
        <Typography.Paragraph>
          The browser talks only to FastAPI. FastAPI runs one agent that was built when the process started. That agent asks Decisions for the route, then asks gpt-6-luna to choose the search arguments and to write. The tools read Postgres. With the live model, Decisions scores each product inside the search, and the cards are streamed before the written answer. The prompt tells the model to name a product only when the tool returned it. The sentence is not scanned.
        </Typography.Paragraph>
        <Mermaid>{REQUEST_PATH}</Mermaid>
      </section>

      <section>
        <Typography.Title level={4}>How a search chooses products</Typography.Title>
        <Typography.Paragraph>
          Read this from top to bottom. A price or rating sort skips the words and the vectors: it filters by category, price, and stock, and an empty category is searched again without that category. Relevance search matches words first. One content word is enough. Words shorter than three letters are dropped, along with a stop list that includes “under” and “something.” A repeated letter is folded, so “phhone” is also searched as “phone.” The match is a substring of the title, description, category, or the joined text that holds the brand and the tags.
        </Typography.Paragraph>
        <Mermaid>{SEARCH_VECTORS}</Mermaid>
        <Typography.Paragraph>
          When the words hit, the order comes from reciprocal rank fusion of the vector ranking and the full-text ranking. Word matches that fusion missed are appended, and the group is cut to four cards. The neighbor score, 1 minus the cosine distance, is a different number: 1 means the same direction, and 0 means unrelated. It is used only in the neighbor step.
        </Typography.Paragraph>
        <Typography.Paragraph>
          If the words miss inside a named category, the same words are tried with the category removed. A hit returns those rows and says the category was dropped. The aisle, highest rated first, is used when that second try also misses, a category was named, and no price was set. Vectors are not used for that aisle.
        </Typography.Paragraph>
        <Typography.Paragraph>
          The neighbor step runs only when the words missed, no aisle was returned, EMBED_MODE=fastembed, and no price was set. The closest row must score at least 0.75, and any other row must sit within 0.05 of that score. Short product texts sit close together, so a vague phrase can fall under 0.75 and leave the card list empty. The useful search is then a category the model passes, such as home decoration, or a product word such as “lamp.” Hash mode never takes this step. A price such as “under 500” filters the word search and does not unlock the neighbor step.
        </Typography.Paragraph>
        <Typography.Paragraph>
          Every search also returns catalog facts: each in-stock category, its price range, the overall price range, and the highest-rated item. The written answer uses those facts. “Cheap” and “cool” are not turned into a price. “A laptop and a watch” is two searches and two groups of cards. “The cheaper one” keeps the earlier cards in the thread and can run a new search sorted by price. That search ignores the query words. The scripted model returns the cheapest in-stock products.
        </Typography.Paragraph>
      </section>

      <section data-testid="diagram-freshness">
        <Typography.Title level={4}>How the catalog stays current</Typography.Title>
        <Typography.Paragraph>
          The remote catalog changes on its own schedule. The copy reads every page into the local table and embeds every product that does not yet have a vector. It does not ask only for products newer than the newest row. Your message is answered from the local table, so a slow remote source does not slow the chat. It only makes the table staler until the next copy.
        </Typography.Paragraph>
        <Mermaid>{FRESHNESS}</Mermaid>
        <Typography.Paragraph>
          The API runs that copy at startup, and on its own timer, when AUTO_SYNC is on. With SYNC_MODE=inprocess, Redis is not required. Celery beat schedules the same full copy from SYNC_INTERVAL_MINUTES, which defaults to 60, and it does not read AUTO_SYNC. Once a day at 03:00 it also reads the remote category list. In Celery mode Redis is the queue and the lock. If Redis is down, that copy is skipped, chat still answers from the current table, and health reports sync as unavailable.
        </Typography.Paragraph>
        <Typography.Paragraph>
          An embedding is the list of numbers stored for a product. Texts with a similar meaning point in a similar direction, so a later search can compare a question with a product by the angle between the two lists. The chat model does not build these lists. A model on this machine does, and they stay in Postgres.
        </Typography.Paragraph>
        <Typography.Paragraph>
          The text behind each list is the title, description, category, brand, and tags, joined into one string. Review comments stay on the product and are left out of that string. A SHA-256 hash of that string is saved with the row. The same hash means the text did not change, and the old list is kept. A new hash clears the list. When the API process starts, a change of embedder clears every list, writes them again, and rebuilds the HNSW index. Otherwise only the empty lists are filled.
        </Typography.Paragraph>
        <Mermaid>{VECTOR_WRITE}</Mermaid>
        <Typography.Paragraph>
          With EMBED_MODE=fastembed the list is 384 numbers from BAAI/bge-small-en-v1.5, running locally. The tests set EMBED_MODE=hash instead, so they do not download that model. Hash mode counts words: each word lands in one of 384 positions, and the list is scaled to length 1. The same word matches. A related word, such as “lamp” and “light,” does not. Both lists are stored in the indexed column. The model is English, so a query in another language ranks poorly.
        </Typography.Paragraph>
      </section>

      <section>
        <Typography.Title level={4}>What is remembered</Typography.Title>
        <Typography.Paragraph>
          The sidebar is a list of chats. The title is the first message, cut at 60 characters. The same title is shown once, as the newest chat. Asking it again from the empty home page opens that chat and does not send the message. Inside a chat, the text is a new turn. Delete removes every chat with that title. The messages, the tool results, and the cards live with that chat, so a reload shows the finished turn. A card whose id is not in a tool result is left out of that reload. With the live model, a long thread is summarized after 6000 tokens and the last 12 messages stay in full.
        </Typography.Paragraph>
      </section>

      {CHOICES.map((choice) => (
        <section key={choice.title}>
          <Typography.Title level={4}>{choice.title}</Typography.Title>
          <Typography.Paragraph>{choice.body}</Typography.Paragraph>
        </section>
      ))}
    </main>
  );
}
