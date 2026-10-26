import { useApiStatus } from './api/useApiStatus';
import { Header } from './components/Header';
import { PipelinePlan } from './components/PipelinePlan';
import { ReadinessPanel } from './components/ReadinessPanel';
import { Card, Tag } from './components/ui';
import { VideoDropzone } from './components/VideoDropzone';
import { Viewport } from './components/Viewport';

export function App() {
  const status = useApiStatus();

  return (
    <>
      <a
        href="#main"
        className="sr-only rounded-button bg-carbon px-4 py-2 text-paper focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-10"
      >
        Skip to content
      </a>
      <Header status={status} />
      <main
        id="main"
        className="mx-auto flex max-w-page flex-col gap-10 px-4 pb-20 sm:px-6 lg:gap-20"
      >
        <section aria-labelledby="hero-heading" className="flex flex-col gap-6 pt-4 lg:pt-8">
          <span className="mono-label text-slate">Mission control / 00</span>
          <h1 id="hero-heading" className="display max-w-[11ch]">
            One pass. Every angle.
          </h1>
          <p className="max-w-xl text-lg text-slate">
            Upload a single drone video. NAZAR reconstructs the scene in 3D and reveals geometry as
            each pipeline stage produces it. Telemetry is optional.
          </p>
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className="flex flex-col gap-6">
            <Card id="missions" aria-labelledby="mission-heading">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id="mission-heading" className="heading">
                  No missions yet
                </h2>
                <Tag tone="mist">Empty</Tag>
              </div>
              <p className="mt-2 mb-6 text-slate">
                Start with the video. Missions are saved once the API stores them.
              </p>
              <VideoDropzone />
            </Card>
            <ReadinessPanel status={status} />
          </div>
          <Viewport />
        </div>

        <PipelinePlan />
      </main>
      <footer className="inverted bg-carbon text-smoke">
        <div className="mx-auto flex max-w-page flex-wrap justify-between gap-4 px-4 py-8 sm:px-6">
          <span className="mono-label">NAZAR · single-pass drone reconstruction</span>
          <span className="mono-label">Outputs are local-frame unless georeferenced</span>
        </div>
      </footer>
    </>
  );
}
