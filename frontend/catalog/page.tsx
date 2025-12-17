/// <reference path="../react-shim.d.ts" />
// "use client" - для Next.js 13+; удалите, если используете CRA/Vite
"use client";

import React, { useEffect, useMemo, useState } from "react";

declare global {
  namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

export type Perfume = {
  id: number;
  name: string;
  brand: string;
  type: string | null;
  volume: string | null;
  description: string | null;
  image: string | null;
  inStock: boolean;
};

const MOCK_PERFUMES: Perfume[] = [
  {
    id: 1,
    brand: "Le Couvent Maison de Parfum",
    name: "Agapi",
    type: "Парфюмированная вода",
    volume: "100 мл",
    description: "Фруктово-цветочный аромат с мягкими цитрусовыми нотами и прозрачной базой.",
    image: "/images/le-couvent-agapi.jpg",
    inStock: true,
  },
  {
    id: 2,
    brand: "Byredo",
    name: "Bal d'Afrique",
    type: "Парфюмированная вода",
    volume: "100 мл",
    description: "Тёплый древесно-ориентальный аромат с яркими цитрусами и цветами.",
    image: "/images/byredo-bal-dafrique.jpg",
    inStock: true,
  },
  {
    id: 3,
    brand: "Wella",
    name: "INVIGO Blond Recharge Шампунь-нейтрализатор желтизны",
    type: "Шампунь",
    volume: "500 мл",
    description: "Фиолетовый шампунь для холодных блондов, устраняет нежелательную жёлтизну.",
    image: "/images/wella-blond-recharge.jpg",
    inStock: true,
  },
  {
    id: 4,
    brand: "Mustela",
    name: "Нежный очищающий гель",
    type: "Гель для тела",
    volume: "500 мл",
    description: "Мягко очищает кожу и волосы малыша, не сушит и не раздражает.",
    image: "/images/mustela-gel.jpg",
    inStock: false,
  },
];

function SearchBar({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input
      className="w-full rounded border px-3 py-2 text-sm"
      placeholder="Поиск по бренду, названию, описанию..."
      value={value}
      onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
    />
  );
}

function ProductCard({ perfume }: { perfume: Perfume }) {
  return (
    <div className="rounded-xl border bg-white shadow-sm overflow-hidden flex flex-col">
      <div className="relative">
        <img
          src={perfume.image || "/images/placeholder.jpg"}
          alt={perfume.name}
          className="w-full h-48 object-cover"
        />
        <span
          className={`absolute top-2 right-2 rounded-full px-3 py-1 text-xs font-semibold ${
            perfume.inStock ? "bg-emerald-500 text-white" : "bg-gray-300 text-gray-700"
          }`}
        >
          {perfume.inStock ? "В наличии" : "Нет в наличии"}
        </span>
      </div>
      <div className="p-4 flex-1 flex flex-col gap-2">
        <div className="text-xs uppercase tracking-wide text-gray-500">{perfume.brand}</div>
        <div className="text-lg font-semibold leading-tight">{perfume.name}</div>
        <div className="text-sm text-gray-600">{perfume.description}</div>
        <div className="text-sm text-gray-500 flex gap-2">
          {perfume.type && <span className="rounded bg-gray-100 px-2 py-1">{perfume.type}</span>}
          {perfume.volume && <span className="rounded bg-gray-100 px-2 py-1">{perfume.volume}</span>}
        </div>
        <div className="mt-auto">
          <button className="w-full rounded-md bg-black text-white py-2 text-sm hover:bg-gray-800">
            Запросить цену
          </button>
        </div>
      </div>
    </div>
  );
}

function ProductGrid({ perfumes }: { perfumes: Perfume[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {perfumes.map((p: Perfume) => (
        <ProductCard key={p.id} perfume={p} />
      ))}
    </div>
  );
}

const alphabet = [
  ..."АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ".split(""),
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ".split(""),
];

function AlphabetFilter({
  selectedLetter,
  onSelectLetter,
}: {
  selectedLetter: string | null;
  onSelectLetter: (letter: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      <button
        className={`px-2 py-1 text-xs rounded ${!selectedLetter ? "bg-black text-white" : "bg-gray-100"}`}
        onClick={() => onSelectLetter(null)}
      >
        Все
      </button>
      {alphabet.map((l: string) => (
        <button
          key={l}
          className={`px-2 py-1 text-xs rounded ${
            selectedLetter === l ? "bg-black text-white" : "bg-gray-100 hover:bg-gray-200"
          }`}
          onClick={() => onSelectLetter(l)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

function BadgeFilter({
  label,
  values,
  selected,
  onToggle,
  onClear,
}: {
  label: string;
  values: string[];
  selected: string[];
  onToggle: (val: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">{label}</div>
        <button className="text-xs text-gray-500" onClick={onClear}>
          сбросить
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {values.map((v) => (
          <button
            key={v}
            className={`px-2 py-1 text-xs rounded-full border ${
              selected.includes(v) ? "bg-black text-white border-black" : "bg-white hover:bg-gray-100"
            }`}
            onClick={() => onToggle(v)}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function CatalogPage() {
  const [query, setQuery] = useState("");
  const [selectedLetter, setSelectedLetter] = useState<string | null>(null);
  const [selectedBrands, setSelectedBrands] = useState<string[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [items, setItems] = useState<Perfume[]>(MOCK_PERFUMES);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query);
      selectedBrands.forEach((b) => params.append("brands", b));
      selectedTypes.forEach((t) => params.append("types", t));
      if (selectedLetter) params.set("letter", selectedLetter);
      try {
        const res = await fetch(`/api/catalog?${params.toString()}`, { signal: controller.signal });
        if (!res.ok) throw new Error("failed");
        const data = await res.json();
        setItems(
          (data?.items || []).map(
            (it: any): Perfume => ({
              id: it.id,
              name: it.name,
              brand: it.brand,
              type: it.type,
              volume: it.volume,
              description: it.description,
              image: it.image,
              inStock: !!it.inStock,
            })
          )
        );
      } catch (e) {
        // если API недоступно — остаёмся на моках
        setItems(MOCK_PERFUMES);
      }
    };
    load();
    return () => controller.abort();
  }, [query, selectedLetter, selectedBrands, selectedTypes]);

  const brands = useMemo(
    () => Array.from(new Set(items.map((p: Perfume) => p.brand).filter((b: string) => Boolean(b)))).sort(),
    [items]
  );
  const types = useMemo(
    () =>
      Array.from(new Set(items.map((p: Perfume) => p.type || "").filter((t: string) => Boolean(t)))).sort(),
    [items]
  );

  const filteredPerfumes = useMemo(() => {
    return items.filter((p: Perfume) => {
      if (query.trim()) {
        const words: string[] = query.toLowerCase().split(/\s+/).filter(Boolean);
        const haystack = `${p.brand} ${p.name} ${p.description || ""}`.toLowerCase();
        if (!words.every((w: string) => haystack.includes(w))) return false;
      }
      if (selectedLetter) {
        const first = p.name.trim()[0]?.toUpperCase();
        if (first !== selectedLetter) return false;
      }
      if (selectedBrands.length > 0 && !selectedBrands.includes(p.brand)) return false;
      if (selectedTypes.length > 0 && !selectedTypes.includes(p.type || "")) return false;
      return true;
    });
  }, [items, query, selectedLetter, selectedBrands, selectedTypes]);

  const handleToggleBrand = (brand: string) => {
    setSelectedBrands((prev: string[]) =>
      prev.includes(brand) ? prev.filter((b: string) => b !== brand) : [...prev, brand]
    );
  };
  const handleToggleType = (type: string) => {
    setSelectedTypes((prev: string[]) =>
      prev.includes(type) ? prev.filter((t: string) => t !== type) : [...prev, type]
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto max-w-6xl px-4 py-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">Каталог ароматов и косметики</h1>
            <p className="text-gray-500 text-sm md:text-base">Поиск по брендам, типам, алфавиту и ключевым словам.</p>
          </div>
          <div className="w-full md:w-80">
            <SearchBar value={query} onChange={setQuery} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 flex gap-6">
        <aside className="hidden lg:block w-72 shrink-0 space-y-6">
          <AlphabetFilter selectedLetter={selectedLetter} onSelectLetter={setSelectedLetter} />
          <hr />
          <BadgeFilter
            label="Бренды"
            values={brands}
            selected={selectedBrands}
            onToggle={handleToggleBrand}
            onClear={() => setSelectedBrands([])}
          />
          <hr />
          <BadgeFilter
            label="Типы"
            values={types}
            selected={selectedTypes}
            onToggle={handleToggleType}
            onClear={() => setSelectedTypes([])}
          />
        </aside>

        <section className="flex-1 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">Найдено позиций: {filteredPerfumes.length}</p>
          </div>
          <ProductGrid perfumes={filteredPerfumes} />
        </section>
      </main>
    </div>
  );
}
