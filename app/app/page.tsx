import TrainsPanel from "@/components/TrainsPanel";

export default function Page() {
  return (
    <main className="page">
      <h1>Is my train running?</h1>
      <p className="intro">Rodalies de Catalunya commuter trains: pick two stations to see the next trains and whether Renfe&apos;s live feed says they are cancelled or late.</p>
      <TrainsPanel />
    </main>
  );
}
