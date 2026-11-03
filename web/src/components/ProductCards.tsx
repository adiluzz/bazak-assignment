import { Card, Image, Rate, Tag, Typography } from "antd";

import type { Product, ProductGroup } from "../api/types";

function money(value: number): string {
  return `$${Number(value).toFixed(2)}`;
}

function struckPrice(product: Product): number | null {
  if (!product.discountPercentage) return null;
  const keep = 1 - product.discountPercentage / 100;
  if (keep <= 0) return null;
  return product.price / keep;
}

export function ProductCards({ groups }: { groups: ProductGroup[] }) {
  if (!groups.length) return null;
  return (
    <div className="card-groups">
      {groups.map((group) => (
        <section key={group.label} className="card-group">
          <Typography.Text strong>{group.label}</Typography.Text>
          {group.note ? <Typography.Paragraph type="secondary">{group.note}</Typography.Paragraph> : null}
          {group.cutoff != null ? (
            <Typography.Paragraph type="secondary">At or below ${Number(group.cutoff).toFixed(2)}.</Typography.Paragraph>
          ) : null}
          <div className="card-grid">
            {group.products.map((product) => {
              const original = struckPrice(product);
              return (
                <Card key={product.id} className="product-card" data-testid="product-card" size="small">
                  <Image src={product.thumbnail} alt={product.title} width="100%" height={120} preview={false} fallback="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" />
                  <Typography.Title level={5} className="product-title">
                    {product.title}
                  </Typography.Title>
                  <Typography.Paragraph ellipsis={{ rows: 2 }} className="product-description">
                    {product.description}
                  </Typography.Paragraph>
                  <div className="product-price">
                    <span>{money(product.price)}</span>
                    {original ? <s>{money(original)}</s> : null}
                  </div>
                  <Rate disabled allowHalf value={product.rating} />
                  <div className="product-meta">
                    <Tag>{product.category}</Tag>
                    <Tag color={product.stock > 0 ? "green" : "red"}>{product.availabilityStatus}</Tag>
                  </div>
                </Card>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
