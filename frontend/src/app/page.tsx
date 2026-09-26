import Link from "next/link";
import {
  ShieldCheck,
  MapPinArea,
  ChartLineUp,
  Database,
  ArrowRight,
  SignIn,
} from "@phosphor-icons/react/dist/ssr";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-background/80 backdrop-blur sticky top-0 z-10">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck weight="fill" className="text-primary" size={28} />
            <div className="flex flex-col leading-tight">
              <span className="font-semibold">NHIC MCI Surveillance</span>
              <span className="text-xs text-muted-foreground">National Health Intelligence Centre</span>
            </div>
          </div>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition"
          >
            Sign in
            <ArrowRight size={16} />
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="container py-24">
        <div className="mx-auto max-w-3xl text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground mb-6">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            Live surveillance active
          </div>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Real-time Mass Casualty Incident monitoring for Rwanda
          </h1>
          <p className="mt-6 text-lg text-muted-foreground">
            Automated media-based surveillance that continuously scrapes,
            classifies and geolocates civilian mass casualty incidents from
            official and journalistic sources, supporting evidence-based
            decision-making at Rwanda&apos;s National Health Intelligence Centre (NHIC).
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:opacity-90 transition"
            >
              <SignIn weight="bold" size={18} />
              Sign in to the dashboard
            </Link>
            <Link
              href="#features"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition"
            >
              Learn more →
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-border bg-muted/30 py-24">
        <div className="container">
          <div className="mx-auto max-w-2xl text-center mb-16">
            <h2 className="text-3xl font-semibold tracking-tight">
              Built for public health decision-making
            </h2>
            <p className="mt-4 text-muted-foreground">
              A complete pipeline from news source to actionable insight.
            </p>
          </div>
          <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
            <FeatureCard
              icon={<Database size={24} weight="duotone" />}
              title="Multi-source ingestion"
              desc="RSS, Google News, and direct scraping across national and international outlets."
            />
            <FeatureCard
              icon={<ShieldCheck size={24} weight="duotone" />}
              title="Three-tier classification"
              desc="Every source graded — Official, Journalism, Other — for credibility-weighted analysis."
            />
            <FeatureCard
              icon={<MapPinArea size={24} weight="duotone" />}
              title="Geographic hotspots"
              desc="36 Rwandan districts geo-tagged, mapped, and ranked by risk score."
            />
            <FeatureCard
              icon={<ChartLineUp size={24} weight="duotone" />}
              title="Trend intelligence"
              desc="Seasonal patterns, year-over-year change, peak-month detection, and rainy-season risk."
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8">
        <div className="container flex items-center justify-between text-xs text-muted-foreground">
          <span>National Health Intelligence Centre (NHIC), Rwanda</span>
          <span>Internal system — authorised personnel only</span>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  desc,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="text-primary mb-4">{icon}</div>
      <h3 className="font-medium mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
    </div>
  );
}
