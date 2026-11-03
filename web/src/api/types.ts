export type Product = {
  id: number;
  title: string;
  description: string;
  category: string;
  price: number;
  discountPercentage: number;
  rating: number;
  stock: number;
  availabilityStatus: string;
  brand: string | null;
  thumbnail: string;
};

export type ProductGroup = {
  label: string;
  products: Product[];
  note?: string;
  cutoff?: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  groups: ProductGroup[];
  status?: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type StreamEvent = {
  type: string;
  text?: string;
  delta?: string;
  group?: ProductGroup;
  message_id?: string;
};
