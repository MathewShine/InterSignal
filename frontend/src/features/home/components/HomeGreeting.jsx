import { motion } from "motion/react";

function getGreeting(hour) {
  if (hour < 12) return "Good morning.";
  if (hour < 17) return "Good afternoon.";
  return "Good evening.";
}

export function HomeGreeting({ environmentLabel, hour = new Date().getHours() }) {
  return (
    <motion.header animate={{ opacity: 1, y: 0 }} className="home-greeting" initial={{ opacity: 0, y: 6 }} transition={{ delay: .1, duration: .28 }}>
      <div>
        <p className="home-greeting__salutation">{getGreeting(hour)}</p>
        <h1>Here’s what matters.</h1>
        <p>Market context, portfolio state and research evidence in one view.</p>
      </div>
      <span className="home-environment-label"><i />{environmentLabel}</span>
    </motion.header>
  );
}
