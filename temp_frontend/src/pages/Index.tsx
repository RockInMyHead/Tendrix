import LandingHeader from "@/components/LandingHeader";
import HeroSection from "@/components/HeroSection";
import HowItWorks from "@/components/HowItWorks";
import Advantages from "@/components/Advantages";
import Pricing from "@/components/Pricing";
import Reviews from "@/components/Reviews";
import MoreInfo from "@/components/MoreInfo";
import Footer from "@/components/Footer";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <LandingHeader />
      <HeroSection />
      <HowItWorks />
      <Advantages />
      <Pricing />
      <Reviews />
      <MoreInfo />
      <Footer />
    </div>
  );
};

export default Index;
