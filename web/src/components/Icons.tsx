import type { SVGProps } from "react";

/** Small line icons, drawn on a 20-unit grid with a 1.6 stroke so they sit with 14-15px text. */
function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

/** Three departments joined by handoffs: the OrgFlow mark and the Overview icon. */
export const MapIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <rect x="2" y="3" width="5" height="4" rx="1" />
    <rect x="13" y="3" width="5" height="4" rx="1" />
    <rect x="7.5" y="13" width="5" height="4" rx="1" />
    <path d="M7 5h6M4.5 7v3.5a2 2 0 0 0 2 2h1M15.5 7v3.5a2 2 0 0 1-2 2h-1" />
  </Icon>
);

export const FlowIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <circle cx="4.5" cy="10" r="2" />
    <circle cx="15.5" cy="10" r="2" />
    <path d="M6.5 10h7M11 7.5 13.5 10 11 12.5" />
  </Icon>
);

export const PlayIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <rect x="3" y="3" width="14" height="14" rx="3" />
    <path d="M8.5 7.2v5.6l4.5-2.8z" />
  </Icon>
);

export const FileIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M5 2.5h6.5L15 6v11.5H5z" />
    <path d="M11.5 2.5V6H15M7.5 10h5M7.5 13h5" />
  </Icon>
);

export const PlusIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M10 4.5v11M4.5 10h11" />
  </Icon>
);

export const BuildingIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M3.5 17V4.5l7-2v14.5M10.5 7h6V17M2 17h16M6 7h1.5M6 10h1.5M6 13h1.5M13 10h1.5M13 13h1.5" />
  </Icon>
);

export const CheckIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="m4.5 10.5 3.5 3.5 7.5-8" />
  </Icon>
);

export const AlertIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M10 3 2.5 16.5h15z" />
    <path d="M10 8.5v3.5M10 14.3v.2" />
  </Icon>
);

export const SparkIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M10 2.5c.6 3.6 1.9 4.9 5.5 5.5-3.6.6-4.9 1.9-5.5 5.5-.6-3.6-1.9-4.9-5.5-5.5 3.6-.6 4.9-1.9 5.5-5.5z" />
    <path d="M15.5 13.5c.3 1.5.8 2 2.3 2.3-1.5.3-2 .8-2.3 2.3-.3-1.5-.8-2-2.3-2.3 1.5-.3 2-.8 2.3-2.3z" />
  </Icon>
);

export const RuleIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M10 3v14M5 6h10M3 12l2-6 2 6a2 2 0 0 1-4 0zM13 12l2-6 2 6a2 2 0 0 1-4 0zM7 17h6" />
  </Icon>
);

export const UploadIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M10 13V3.5M6 7.5l4-4 4 4M3.5 13v3.5h13V13" />
  </Icon>
);

export const PrintIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M6 7V2.5h8V7M6 14.5H3.5V7h13v7.5H14M6 11.5h8v6H6z" />
  </Icon>
);

/** The OrgFlow mark: a small indigo tile with the map glyph. */
export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-ai text-sheet shadow-[0_2px_6px_rgb(79_70_229/0.35)]">
        <MapIcon width="18" height="18" strokeWidth="1.8" />
      </span>
      <span className="text-lg font-semibold tracking-tight">OrgFlow</span>
    </span>
  );
}
