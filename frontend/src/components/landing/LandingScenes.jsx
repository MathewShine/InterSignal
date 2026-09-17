import { PublicFooter } from "../public/PublicFooter.jsx";
import { ConvergenceFocusScene } from "./ConvergenceScene.jsx";
import { PortfolioContextScene } from "./PortfolioStage.jsx";
import { ReassemblyScene } from "./ReassemblyScene.jsx";
import { PerspectiveSeparationScene } from "./SharedProductScene.jsx";

export default function LandingScenes() {
  return (
    <>
      <PerspectiveSeparationScene />
      <div aria-hidden="true" className="scene-boundary-gap scene-boundary-gap--light" data-boundary="light-dark" />
      <ConvergenceFocusScene />
      <div aria-hidden="true" className="scene-boundary-gap scene-boundary-gap--dark" data-boundary="dark-sky" />
      <PortfolioContextScene />
      <ReassemblyScene />
      <PublicFooter />
    </>
  );
}
