import React from 'react';
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import { useNavigate } from 'react-router-dom';

interface BreadcrumbItem {
  text: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export default function Breadcrumb({ items }: BreadcrumbProps) {
  const navigate = useNavigate();

  return (
    <BreadcrumbGroup
      items={items}
      onFollow={(event) => {
        event.preventDefault();
        if (event.detail.href) {
          navigate(event.detail.href);
        }
      }}
    />
  );
}