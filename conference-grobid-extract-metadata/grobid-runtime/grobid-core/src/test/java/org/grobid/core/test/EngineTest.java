package org.grobid.core.test;

import org.junit.AfterClass;
import org.junit.BeforeClass;

import org.grobid.core.engines.Engine;
import org.grobid.core.factory.GrobidFactory;

public abstract class EngineTest {
    protected static Engine engine;

    @BeforeClass
    public static void setUpClass() throws Exception {
        engine = GrobidFactory.getInstance().getEngine();
    }

    @AfterClass
    public static void closeResources() throws Exception {
        engine.close();
    }
}
