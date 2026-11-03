export const ONE_TURN = `flowchart TD
  msg["1. You send a message"]
  route["2. Decisions picks the route from the last six messages"]
  search["Search: find that product"]
  clarify["Clarify: search, then ask one question"]
  off["Off catalog: do not search"]
  chat["Chat: do not search"]
  found["3. Postgres returns matches plus the categories and prices"]
  review["4. Live model: drop a product that does not answer. Scripted mode skips this"]
  cards["5. Stream the cards, then the written answer"]
  words["5. Stream a short reply and no cards"]
  msg --> route
  route --> search
  route --> clarify
  route --> off
  route --> chat
  search --> found
  clarify --> found
  found --> review
  review --> cards
  off --> words
  chat --> words`;

export const REQUEST_PATH = `flowchart TD
  browser["Your browser"]
  api["FastAPI receives the message"]
  agent["The shopping agent, built once at startup"]
  decisions["Decisions API chooses the route"]
  args["gpt-6-luna chooses the search arguments"]
  tools["search_products first. list_categories lists names"]
  db["Postgres: products, vectors, and this chat"]
  review["Decisions scores each product. Scripted mode skips this"]
  write["gpt-6-luna writes the reply"]
  browser -->|"the message"| api
  api --> agent
  agent --> decisions
  decisions --> args
  args --> tools
  tools --> db
  db --> review
  review --> write
  api -->|"status, then cards, then tokens"| browser`;

export const FRESHNESS = `flowchart TD
  clock["A timer, every SYNC_INTERVAL_MINUTES"]
  boot["API startup, when AUTO_SYNC is on"]
  worker["The copy job"]
  remote["The remote catalog"]
  save["Save every product from those pages"]
  embed["Embed every product that has no vector"]
  table["The local products table"]
  turn["A shopper message reads only this table"]
  clock --> worker
  boot --> worker
  worker -->|"every page, on each run"| remote
  remote -->|"a page of products"| worker
  worker --> save
  save --> embed
  embed --> table
  table --> turn`;

export const VECTOR_WRITE = `flowchart TD
  save["A product is saved"]
  text["Join title, description, category, brand, and tags into one text"]
  digest["Hash that text"]
  same{"Same hash as the stored row?"}
  keep["Keep the vector already stored"]
  clear["Clear the vector"]
  boot["The API process starts"]
  switched{"Embedder different from last startup?"}
  wipe["Clear every vector"]
  empty["Rows whose vector is empty"]
  which{"Which embedder is configured?"}
  live["Local model writes 384 numbers"]
  hashed["Tests: each word fills one of 384 buckets"]
  column["Store the list on the product row"]
  index["HNSW index, compared by angle"]
  save --> text --> digest --> same
  same -->|unchanged| keep --> index
  same -->|text changed| clear --> empty
  boot --> switched
  switched -->|no| empty
  switched -->|yes| wipe --> empty
  empty --> which
  which -->|fastembed| live --> column
  which -->|hash| hashed --> column
  column --> index`;

export const SEARCH_VECTORS = `flowchart TD
  tool["search_products gets a query, a category, a price, and a sort"]
  priced{"Sort by price or rating?"}
  plain["Filter by category, price, and stock. Ignore the query words"]
  words["Match any content word in the product text"]
  hit{"Any row contains one of those words?"}
  fuse["Fuse the vector rank with the full-text rank"]
  cards["At most 4 cards"]
  named{"A category was named?"}
  retry["Search those words again with no category"]
  again{"Any row now?"}
  dropped["Return those rows and say the category was dropped"]
  aisle{"No price, and that aisle has products?"}
  browse["Return that aisle, highest rated first"]
  semantic{"Live embedder, and no price filter?"}
  nearest["Embed the query and take the nearest stored vectors"]
  strong{"Closest score at least 0.75, and the rest within 0.05?"}
  none["No cards"]
  tool --> priced
  priced -->|yes| plain --> cards
  priced -->|relevance| words --> hit
  hit -->|yes| fuse --> cards
  hit -->|no| named
  named -->|yes| retry --> again
  again -->|yes| dropped --> cards
  again -->|no| aisle
  named -->|no| semantic
  aisle -->|yes| browse --> cards
  aisle -->|no| semantic
  semantic -->|yes| nearest --> strong
  strong -->|yes| cards
  strong -->|too weak| none
  semantic -->|"hash mode, or a price was set"| none`;
