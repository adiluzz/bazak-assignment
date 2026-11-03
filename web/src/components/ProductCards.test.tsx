import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProductCards } from "./ProductCards";

describe("ProductCards", () => {
  it("shows title, description, price, and image", () => {
    render(
      <ProductCards
        groups={[
          {
            label: "Phones",
            products: [
              {
                id: 2,
                title: "Galaxy Budget",
                description: "An affordable phone.",
                category: "smartphones",
                price: 199,
                discountPercentage: 10,
                rating: 4.2,
                stock: 20,
                availabilityStatus: "In Stock",
                brand: "Samsung",
                thumbnail: "https://example.test/2.jpg",
              },
            ],
          },
        ]}
      />,
    );
    expect(screen.getByText("Galaxy Budget")).toBeInTheDocument();
    expect(screen.getByText("An affordable phone.")).toBeInTheDocument();
    expect(screen.getByText("$199.00")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Galaxy Budget" })).toHaveAttribute("src", "https://example.test/2.jpg");
  });
});
