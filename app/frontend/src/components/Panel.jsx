import { useRef } from "react";
import { useStore } from "../App.jsx";
import { Logo } from "../icons.jsx";
import ThemeToggle from "./ThemeToggle.jsx";
import SearchBox from "./SearchBox.jsx";
import ServicePicker from "./ServicePicker.jsx";
import LocationInputs from "./LocationInputs.jsx";
import Results from "./Results.jsx";
import DetailsDrawer from "./DetailsDrawer.jsx";

export default function Panel() {
  const { setModalOpen } = useStore();
  const scrollRef = useRef(null);
  return (
    <aside className="panel" id="panel">
      <div className="panel-scroll" id="panel-scroll" ref={scrollRef}>
        <header className="head">
          <div className="brand">
            <span className="logo" aria-hidden="true"><Logo /></span>
            <div>
              <h1>Care finder</h1>
              <p className="sub">Nearby facilities for a medical service, with the quoted evidence behind each one.</p>
            </div>
          </div>
          <div className="head-actions">
            <button className="text-btn" type="button" onClick={() => setModalOpen(true)}>How this works</button>
            <ThemeToggle />
          </div>
        </header>
        <section className="search">
          <SearchBox />
          <ServicePicker />
          <LocationInputs />
        </section>
        <Results scrollRef={scrollRef} />
      </div>
      <DetailsDrawer />
    </aside>
  );
}
